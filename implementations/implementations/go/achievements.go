package main

import (
	"fmt"
	"math"
	"sort"
	"strings"
)

const achievementEventKind = "r2t_achievement_delivery"
const achievementHistory = "r2t_achievements"

type Milestones struct {
	App    *App
	Sender *Sender
	Lease  *Lease
}

func containsID(values A, wanted int64) bool {
	for _, value := range values {
		if n, e := whole(value); e == nil && n == wanted {
			return true
		}
	}
	return false
}
func (s *Milestones) report(body, mode string) {
	if _, e := s.Sender.text(body, false, mode); e != nil {
		logInfo("Could not send achievement sweep status")
	}
}
func (s *Milestones) queue(module, handle string, achievement int64) error {
	channel := lower(handle)
	legacy, e := s.App.DB.one("settings", D{"setting": achievementHistory}, nil)
	if e != nil {
		return e
	}
	if value, exists := legacy["channels"]; exists {
		channels, ok := value.(D)
		if !ok {
			return fault("Config")
		}
		if _, exists := channels[channel]; exists {
			previous, e := identifiers(channels, channel)
			if e != nil {
				return e
			}
			if containsID(previous, achievement) {
				return nil
			}
		}
	}
	id := fmt.Sprintf("%s:%s:%d", achievementEventKind, channel, achievement)
	_, e = s.App.DB.update("settings", D{"_id": id}, D{"$setOnInsert": D{"setting": id, "kind": achievementEventKind, "submodule": module,
		"channel": channel, "achievement": achievement, "complete": false, "message_ids": A{}, "forwarded_ids": A{}, "created_at": date(now())}}, false, true)
	return e
}
func (s *Milestones) candidate(event D, checkpoint *Checkpoint, postingAttempted *bool) error {
	module, ok := at(event, "submodule").(string)
	if !ok {
		return fault("Config")
	}
	channel, ok := at(event, "channel").(string)
	if !ok {
		return fault("Config")
	}
	source, e := s.App.resolve(module)
	if e != nil {
		return e
	}
	achievement, e := whole(at(event, "achievement"))
	if e != nil {
		return e
	}
	heading := fmt.Sprintf("🏆 Great achievement!\n%s\n💪 Milestone of %d subscribers.\n\n", channel, achievement)
	reddit := newReddit(s.App.Config, s.Sender.Metrics)
	defer reddit.close()
	target := s.App.sender(mainChannel, s.Sender.Metrics)
	defer target.close()
	target.Ack = checkpoint.record
	scanned, after, stop := 0, "", false
	for scanned < 1000 && !stop {
		var page D
		for retries := 0; retries < 10; retries++ {
			page, e = reddit.listing(source.Subreddit, "top", 1000, after)
			if e == nil {
				break
			}
			if retries == 9 {
				return e
			}
			s.Sender.Metrics.count("reddit_listing_retries", 1)
			longSleep(2.818281828 * math.Pi / 2)
		}
		items, ok := at(at(page, "data"), "children").([]any)
		if !ok {
			return fault("Reddit")
		}
		if len(items) == 0 {
			break
		}
		for _, item := range items {
			if scanned >= 1000 {
				break
			}
			scanned++
			submission := doc(at(item, "data"))
			link := "https://redd.it/" + field(submission, "id")
			seen, e := target.seen(link)
			if e != nil {
				return e
			}
			if seen {
				continue
			}
			blocked, e := target.errorLimit(link)
			if e != nil {
				return e
			}
			if blocked {
				continue
			}
			*postingAttempted = true
			result, e := nice(s.App, module, submission, target, reddit, heading, "", channel)
			if e != nil {
				return e
			}
			if len(checkpoint.ids()) > 0 && result != Sent {
				result = Stop
			}
			switch result {
			case Sent:
				if e = target.mark(link, true); e != nil {
					return e
				}
				stop = true
			case Reject:
				if e = target.mark(link, false); e != nil {
					return e
				}
			case Stop:
				stop = true
			}
			if stop {
				break
			}
		}
		after = field(at(page, "data"), "after")
		if after == "" {
			break
		}
	}
	return nil
}
func (s *Milestones) deliver(event D) error {
	if e := s.Lease.renew(); e != nil {
		return e
	}
	id, exists := event["_id"]
	channel, ok := at(event, "channel").(string)
	if !exists || !ok {
		return fault("Config")
	}
	selector := D{"_id": id}
	achievement, e := whole(at(event, "achievement"))
	if e != nil {
		return e
	}
	if _, e = s.App.DB.update("settings", selector, D{"$inc": D{"attempts": 1}, "$set": D{"last_attempt_at": date(now())}}, false, false); e != nil {
		return e
	}
	recorded, e := identifiers(event, "message_ids")
	if e != nil {
		return e
	}
	checkpoint := newCheckpoint(s.App.DB, selector, "", recorded)
	if len(checkpoint.ids()) == 0 {
		attempted := false
		e = s.candidate(event, checkpoint, &attempted)
		if e != nil && len(checkpoint.ids()) == 0 && attempted {
			return e
		}
		if len(checkpoint.ids()) == 0 {
			target := s.App.sender(mainChannel, s.Sender.Metrics)
			defer target.close()
			target.Ack = checkpoint.record
			result, e := target.text(fmt.Sprintf("🏆 Great achievement!\n%s\n💪 Milestone of %d subscribers.", channel, achievement), false, "")
			if e != nil {
				return e
			}
			if result != Sent || len(checkpoint.ids()) == 0 {
				return fault("Announcement")
			}
		}
	}
	if e = s.Lease.renew(); e != nil {
		return e
	}
	ids := checkpoint.ids()
	if _, e = s.App.DB.update("settings", selector, D{"$addToSet": D{"message_ids": D{"$each": ids}}}, false, false); e != nil {
		return e
	}
	if _, e = s.App.DB.update("settings", D{"setting": achievementHistory}, D{"$addToSet": D{"channels." + channel: achievement}}, false, true); e != nil {
		return e
	}
	if channel != mainChannel {
		forwarded, e := identifiers(event, "forwarded_ids")
		if e != nil {
			return e
		}
		target := s.App.sender(channel, s.Sender.Metrics)
		defer target.close()
		for _, value := range ids {
			id, e := whole(value)
			if e != nil {
				return e
			}
			if containsID(forwarded, id) {
				continue
			}
			if e = s.Lease.renew(); e != nil {
				return e
			}
			if _, e = target.api("forwardMessage", D{"chat_id": channel, "from_chat_id": mainChannel, "message_id": id}); e != nil {
				return e
			}
			if _, e = s.App.DB.update("settings", selector, D{"$addToSet": D{"forwarded_ids": id}}, false, false); e != nil {
				return e
			}
		}
	}
	_, e = s.App.DB.update("settings", selector, D{"$set": D{"complete": true, "completed_at": date(now())}}, false, false)
	return e
}

type Snapshot struct {
	Channel         string
	Before, Current int64
}
type Totals struct{ Channels, Members, Admins, Errors, Previous int64 }

func signText(n int64) string {
	if n < 0 {
		return ""
	}
	if n == 0 {
		return "±"
	}
	return "+"
}
func percentage(difference, before int64) string {
	if before == 0 {
		return "0"
	}
	value := fmt.Sprintf("%.2f", float64(difference)/float64(before)*100)
	value = strings.TrimRight(value, "0")
	if strings.HasSuffix(value, ".") {
		value += "0"
	}
	return value
}
func leaderboard(heading string, snapshots []Snapshot, gains bool) string {
	sorted := append([]Snapshot{}, snapshots...)
	sort.SliceStable(sorted, func(i, j int) bool {
		a, b := sorted[i].Current-sorted[i].Before, sorted[j].Current-sorted[j].Before
		if gains {
			return a > b
		}
		return a < b
	})
	for _, row := range sorted[:min(5, len(sorted))] {
		delta := row.Current - row.Before
		symbol := signText(delta)
		heading += fmt.Sprintf("%s: %d %s%d (%s%s%%) → %d\n", row.Channel, row.Before, symbol, delta, symbol, percentage(delta, row.Before), row.Current)
	}
	return heading
}
func (s *Milestones) collectAdmins(channel string, snapshot D, totals *Totals) error {
	value, e := s.Sender.api("getChatAdministrators", D{"chat_id": channel})
	if e != nil {
		return e
	}
	admins, ok := value.([]any)
	if !ok {
		return fault("Telegram")
	}
	names := A{}
	for _, admin := range admins {
		if name, ok := at(at(admin, "user"), "username").(string); ok {
			if name != "reddit2telegram_bot" {
				names = append(names, "@"+name)
			}
		} else {
			names = append(names, "%NO_USERNAME%")
		}
	}
	totals.Admins += int64(len(names))
	snapshot["admins"] = names
	return nil
}
func (s *Milestones) collectMembers(module, channel string, snapshot D, totals *Totals, thresholds A, snapshots *[]Snapshot) error {
	value, e := s.Sender.api("getChatMemberCount", D{"chat_id": channel})
	if e != nil {
		return e
	}
	members, e := whole(value)
	if e != nil {
		return e
	}
	previous, e := s.App.DB.one("stats", D{"channel": lower(channel), "members_cnt": D{"$gte": 0}}, D{"ts": -1})
	if e != nil {
		return e
	}
	before := members
	if previous != nil {
		before, e = whole(at(previous, "members_cnt"))
		if e != nil {
			return e
		}
	}
	for _, value := range thresholds {
		threshold, e := whole(value)
		if e != nil {
			return e
		}
		if before < threshold && threshold <= members {
			if e = s.queue(module, channel, threshold); e != nil {
				return e
			}
		}
	}
	snapshot["members_cnt"] = members
	if e = s.App.DB.insert("stats", A{snapshot}); e != nil {
		return e
	}
	totals.Members += members
	totals.Previous += before
	*snapshots = append(*snapshots, Snapshot{channel, before, members})
	return nil
}
func (s *Milestones) sweep() error {
	s.report("Regular bypass started.", "")
	value, e := parse(asset("milestones"))
	if e != nil {
		return e
	}
	thresholds, e := identifiers(D{"ids": value}, "ids")
	if e != nil {
		return e
	}
	modules, e := s.App.publicModules()
	if e != nil {
		return e
	}
	coefficient := 2000.0 / 3 / 2 / float64(max(1, len(modules)))
	for i := len(modules); i > 1; i-- {
		j := randomIndex(i)
		modules[i-1], modules[j] = modules[j], modules[i-1]
	}
	totals := Totals{}
	snapshots := []Snapshot{}
	seen := map[string]bool{}
	for _, module := range modules {
		if e = s.Lease.renew(); e != nil {
			return e
		}
		shortSleep(coefficient)
		resolved, e := s.App.resolve(module)
		if e != nil {
			totals.Errors++
			continue
		}
		channel, ok := resolved.Destination.(string)
		if !ok || !strings.HasPrefix(channel, "@") || seen[lower(channel)] {
			continue
		}
		seen[lower(channel)] = true
		snapshot := D{"channel": lower(channel), "ts": date(now()), "submodule": module}
		totals.Channels++
		if e = s.collectAdmins(channel, snapshot, &totals); e != nil {
			totals.Errors++
			s.report("Failed to get admins for "+channel+".", "")
		}
		shortSleep(coefficient)
		if e = s.collectMembers(module, channel, snapshot, &totals, thresholds, &snapshots); e != nil {
			totals.Errors++
			s.report("Failed to collect statistics or queue milestones for "+channel+".", "")
		}
	}
	events, e := s.App.DB.find("settings", D{"kind": achievementEventKind, "complete": false}, nil, 0, nil)
	if e != nil {
		return e
	}
	for _, value := range events {
		if e = s.Lease.renew(); e != nil {
			return e
		}
		event := doc(value)
		if e = s.deliver(event); e != nil {
			totals.Errors++
			if at(event, "_id") == nil {
				return fault("Config")
			}
			channel, ok := at(event, "channel").(string)
			if !ok {
				return fault("Config")
			}
			if _, err := s.App.DB.update("settings", D{"_id": at(event, "_id")}, D{"$set": D{"last_error_type": safe(e).Kind, "last_failure_at": date(now())}}, false, false); err != nil {
				return err
			}
			number, e := whole(at(event, "achievement"))
			if e != nil {
				return e
			}
			s.report(fmt.Sprintf("Milestone delivery pending: %s, %d subscribers.", channel, number), "")
		}
	}
	difference := totals.Members - totals.Previous
	symbol := signText(difference)
	s.report(fmt.Sprintf("Ok, regular bypass results.\n\n<pre>Active channels: %d.</pre>\n<pre>Subscribers: %d.</pre>\n<pre>Cnt diff: %s%d (%s%s%%).</pre>\n<pre>Admins: %d.</pre>\n<pre>Errors during bypass: %d.</pre>\n\n<i>See you!</i>", totals.Channels, totals.Members, symbol, difference, symbol, percentage(difference, totals.Previous), totals.Admins, totals.Errors), "HTML")
	shortSleep(1)
	s.report(leaderboard("📈 <b>TOP 5 GAIN</b> 📈\n", snapshots, true), "HTML")
	shortSleep(1)
	s.report(leaderboard("📉 <b>TOP 5 FALL</b> 📉\n", snapshots, false), "HTML")
	return nil
}
func achievements(app *App, sender *Sender) (Supply, error) {
	service := &Milestones{App: app, Sender: sender, Lease: newLease(app.DB, "r2t_achievement_sweep_lock")}
	acquired, e := service.Lease.acquire()
	if e != nil {
		return Skip, e
	}
	if !acquired {
		return Stop, nil
	}
	outcome := func() (e error) {
		defer func() {
			if recover() != nil {
				e = fault("NativeError")
			}
		}()
		return service.sweep()
	}()
	if e = service.Lease.release(); e != nil && outcome == nil {
		outcome = e
	}
	if outcome != nil {
		return Skip, outcome
	}
	return Stop, nil
}
