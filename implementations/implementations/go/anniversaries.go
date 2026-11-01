package main

import (
	"fmt"
	"regexp"
	"sort"
	"strings"
	"time"
)

const dateKind = "r2t_anniversary_date"
const anniversaryEventKind = "r2t_anniversary_delivery"
const anniversaryRunKind = "r2t_anniversary_run"
const mainChannel = "@reddit2telegram"
const community = "@r_channels"

func midnight(value any) (float64, error) {
	if stamp, ok := timestamp(value); ok {
		t := parts(stamp, true)
		return float64(time.Date(t.Year(), t.Month(), t.Day(), 0, 0, 0, 0, time.UTC).Unix()), nil
	}
	if text, ok := value.(string); ok {
		if t, e := time.Parse("2006-01-02", text); e == nil && t.Format("2006-01-02") == text {
			return float64(t.Unix()), nil
		}
	}
	return 0, fault("Config")
}
func chatKey(value any) string {
	if s, ok := value.(string); ok {
		return lower(s)
	}
	return dump(value)
}
func bump(record D, key string)   { record[key] = int64(num(at(record, key), 0)) + 1 }
func pushError(record D, value D) { record["errors"] = append(arr(at(record, "errors")), value) }
func anniversaryMessages(channel string, years int, channels []string, today float64) []string {
	plural := "s"
	if years == 1 {
		plural = ""
	}
	intro := fmt.Sprintf("🌍 <b>Discover the Reddit2Telegram family</b>\n\n📣 @reddit2telegram — our main channel for discovering posts and channels from across the network.\n\n💬 @r_channels — join the community, find new channels, ask questions, and suggest your next favorite.\n\n🎂 <b>Celebrating %s: %d year%s together!</b>\n📅 %s\nThank you for reading, sharing, and being part of the community. Here’s to another year of great discoveries!", htmlEscape(channel), years, plural, timeText(today, "02 January 2006", true))
	unique := map[string]bool{}
	for _, name := range channels {
		c := lower(name)
		if c != lower(channel) && c != mainChannel && c != community && c != "@r_channels_test" {
			unique[c] = true
		}
	}
	others := []string{}
	for c := range unique {
		others = append(others, c)
	}
	sort.Strings(others)
	if len(others) == 0 {
		return []string{intro}
	}
	intro += "\n\n🧭 Explore more of our channels in the directory below."
	pages := []string{}
	lines := []string{}
	for i, c := range others {
		line := fmt.Sprintf("%d. %s", i+1, htmlEscape(c))
		candidate := strings.Join(append(append([]string{}, lines...), line), "\n")
		if len(lines) > 0 && (len(lines) == 100 || utf16Count(candidate) > 3400) {
			pages = append(pages, strings.Join(lines, "\n"))
			lines = nil
		}
		lines = append(lines, line)
	}
	if len(lines) > 0 {
		pages = append(pages, strings.Join(lines, "\n"))
	}
	out := []string{intro}
	for i, page := range pages {
		out = append(out, fmt.Sprintf("🧭 <b>More channels · %d/%d</b>\n\n%s", i+1, len(pages), page))
	}
	return out
}

type Anniversary struct {
	App    *App
	Sender *Sender
	Lease  *Lease
}

func (s *Anniversary) birthday(channel string, record D) (float64, bool, error) {
	id := dateKind + ":" + channel
	filter := D{"_id": id}
	cached, e := s.App.DB.one("settings", filter, nil)
	if e != nil {
		return 0, false, e
	}
	explicit := at(record, "anniversary_date")
	var birthday float64
	source := ""
	if explicit != nil {
		birthday, e = midnight(explicit)
		if e != nil {
			return 0, false, e
		}
		source = "explicit"
	} else if cached != nil {
		birthday, e = midnight(at(cached, "date"))
		return birthday, true, e
	} else {
		rows, e := s.App.DB.find("urls", D{"channel": channel, "sent": true, "ts": D{"$type": "date"}}, D{"ts": 1}, 1, D{"ts": 1})
		if e != nil {
			return 0, false, e
		}
		if len(rows) == 0 {
			return 0, false, nil
		}
		birthday, e = midnight(at(rows[0], "ts"))
		if e != nil {
			return 0, false, e
		}
		source = "first_sent_post"
	}
	values := D{"setting": id, "kind": dateKind, "channel": channel, "date": date(birthday), "source": source}
	operation := "$setOnInsert"
	if explicit != nil {
		operation = "$set"
	}
	_, e = s.App.DB.update("settings", filter, D{operation: values}, false, true)
	return birthday, true, e
}
func (s *Anniversary) inventory(run D) ([]string, []float64, error) {
	local, e := parse(asset("local_channels"))
	if e != nil {
		return nil, nil, e
	}
	modules, e := s.App.publicModules()
	if e != nil {
		return nil, nil, e
	}
	handles := regexp.MustCompile(`^@[a-zA-Z][a-zA-Z0-9_]{4,31}$`)
	seen := map[string]bool{}
	names := []string{}
	birthdays := []float64{}
	for _, module := range modules {
		if e = s.Lease.renew(); e != nil {
			return nil, nil, e
		}
		channel, stamp, found, inspectErr := func() (string, float64, bool, error) {
			record, e := s.App.DB.one("channels", D{"submodule": module}, nil)
			if e != nil {
				return "", 0, false, e
			}
			var value any
			if record != nil {
				value = at(record, "channel")
			} else {
				entry, ok := at(local, module).(D)
				if !ok {
					return "", 0, false, fault("Config")
				}
				value = at(entry, "t_channel")
			}
			channel, ok := value.(string)
			if !ok || !handles.MatchString(channel) {
				return "", 0, false, nil
			}
			channel = lower(channel)
			if channel == community || channel == "@r_channels_test" || seen[channel] {
				return "", 0, false, nil
			}
			stamp, found, e := s.birthday(channel, record)
			return channel, stamp, found, e
		}()
		if inspectErr != nil {
			pushError(run, D{"submodule": module, "error_type": safe(inspectErr).Kind})
			continue
		}
		if channel == "" {
			continue
		}
		if found {
			seen[channel] = true
			names = append(names, channel)
			birthdays = append(birthdays, stamp)
		} else {
			logInfo("Anniversary skipped: " + channel + " has no successful posting history")
			run["skipped_no_history"] = append(arr(at(run, "skipped_no_history")), channel)
		}
	}
	return names, birthdays, nil
}
func (s *Anniversary) queue(channel string, years int, today float64, channels []string) error {
	year := parts(today, true).Year()
	id := fmt.Sprintf("%s:%s:%d", anniversaryEventKind, channel, year)
	plural := "s"
	if years == 1 {
		plural = ""
	}
	notice := fmt.Sprintf("🎂 <b>Celebrating %s: %d year%s together!</b>\n📅 %s\n\nDiscover this channel and more in our main feed @reddit2telegram.\nJoin @r_channels to explore the network and meet the community.", htmlEscape(channel), years, plural, timeText(today, "02 January 2006", true))
	deliveries := A{}
	for _, body := range anniversaryMessages(channel, years, channels, today) {
		deliveries = append(deliveries, D{"destination": channel, "text": body, "state": "pending"})
	}
	destinations := map[string]bool{lower(channel): true}
	targets := A{mainChannel, community, at(at(s.App.Config.Values, "telegram"), "dev_chat")}
	for _, destination := range targets {
		key := chatKey(destination)
		if !destinations[key] {
			destinations[key] = true
			deliveries = append(deliveries, D{"destination": destination, "text": notice, "state": "pending"})
		}
	}
	_, e := s.App.DB.update("settings", D{"_id": id}, D{"$setOnInsert": D{"setting": id, "kind": anniversaryEventKind, "channel": channel, "year": year, "years": years,
		"anniversary": timeText(today, "2006-01-02", true), "created_at": date(now()), "complete": false, "deliveries": deliveries}}, false, true)
	return e
}
func (s *Anniversary) deliver(event D) (bool, error) {
	deliveries, ok := at(event, "deliveries").([]any)
	if !ok || at(event, "_id") == nil {
		return false, fault("Config")
	}
	id := at(event, "_id")
	blocked := map[string]bool{}
	for index, value := range deliveries {
		if e := s.Lease.renew(); e != nil {
			return false, e
		}
		delivery := doc(value)
		destination, exists := delivery["destination"]
		state, ok := at(delivery, "state").(string)
		if !exists || !ok {
			return false, fault("Config")
		}
		key := dump(destination)
		path := fmt.Sprintf("deliveries.%d", index)
		if state == "sent" || blocked[key] {
			continue
		}
		if state == "sending" || state == "uncertain" {
			if _, e := s.App.DB.update("settings", D{"_id": id, path + ".state": "sending"}, D{"$set": D{path + ".state": "uncertain"}}, false, false); e != nil {
				return false, e
			}
			blocked[key] = true
			continue
		}
		attempt := uuid()
		claimed, e := s.App.DB.update("settings", D{"_id": id, path + ".state": "pending"}, D{"$set": D{path + ".state": "sending", path + ".attempt": attempt, path + ".attempted_at": date(now())}, "$inc": D{path + ".attempts": 1}}, false, false)
		if e != nil {
			return false, e
		}
		if num(at(claimed, "n"), 0) == 0 {
			blocked[key] = true
			continue
		}
		selector := D{"_id": id, path + ".attempt": attempt}
		checkpoint := newCheckpoint(s.App.DB, selector, path, nil)
		target := s.Sender.clone(destination)
		target.Ack = checkpoint.record
		result := Skip
		body, valid := at(delivery, "text").(string)
		if valid {
			result, e = target.text(body, true, "HTML")
		} else {
			e = fault("Config")
		}
		if e == nil && (result != Sent || len(checkpoint.ids()) == 0) {
			e = fault("Announcement")
		}
		if e != nil {
			if len(checkpoint.ids()) > 0 {
				if err := checkpoint.record(A{}); err != nil {
					return false, err
				}
			} else {
				kind := safe(e).Kind
				retryable := kind == "Rejected" || kind == "Forbidden" || kind == "RateLimit"
				next := "uncertain"
				if retryable {
					next = "pending"
				}
				if _, err := s.App.DB.update("settings", selector, D{"$set": D{path + ".state": next, path + ".last_error_type": kind}}, false, false); err != nil {
					return false, err
				}
			}
			blocked[key] = true
		}
		shortSleep(1)
	}
	current, e := s.App.DB.one("settings", D{"_id": id}, nil)
	if e != nil {
		return false, e
	}
	parts, ok := at(current, "deliveries").([]any)
	if !ok {
		return false, fault("Database")
	}
	complete := true
	for _, part := range parts {
		if field(part, "state") != "sent" {
			complete = false
		}
	}
	_, e = s.App.DB.update("settings", D{"_id": id}, D{"$set": D{"complete": complete, "updated_at": date(now())}}, false, false)
	return complete, e
}
func (s *Anniversary) sweep(run D, acquired *bool) error {
	var e error
	*acquired, e = s.Lease.acquire()
	if e != nil {
		return e
	}
	if !*acquired {
		run["status"] = "skipped_overlap"
		return nil
	}
	if s.Lease.HasPrevious {
		_, e = s.App.DB.update("settings", D{"kind": anniversaryRunKind, "owner": s.Lease.PreviousOwner, "status": "running", "_id": D{"$ne": at(run, "_id")}},
			D{"$set": D{"status": "interrupted", "finished_at": date(now()), "errors": A{D{"error_type": "InterruptedSweep"}}}}, true, false)
		if e != nil {
			return e
		}
	}
	names, birthdays, e := s.inventory(run)
	if e != nil {
		return e
	}
	active := map[string]bool{}
	for _, name := range names {
		active[name] = true
	}
	run["channels"] = len(names)
	today, e := midnight(at(run, "date"))
	if e != nil {
		return e
	}
	current := parts(today, true)
	year := current.Year()
	for i, channel := range names {
		if e = s.Lease.renew(); e != nil {
			return e
		}
		born := parts(birthdays[i], true)
		month, day := born.Month(), born.Day()
		leap := year%4 == 0 && (year%100 != 0 || year%400 == 0)
		if month == 2 && day == 29 && !leap {
			day = 28
		}
		years := year - born.Year()
		if years > 0 && current.Month() == month && current.Day() == day {
			bump(run, "due")
			if e = s.queue(channel, years, today, names); e != nil {
				return e
			}
		}
	}
	filter := D{"kind": anniversaryEventKind, "complete": false}
	events, e := s.App.DB.find("settings", filter, nil, 0, nil)
	if e != nil {
		return e
	}
	for _, value := range events {
		if e = s.Lease.renew(); e != nil {
			return e
		}
		event := doc(value)
		channel, ok := at(event, "channel").(string)
		if !ok {
			return fault("Config")
		}
		if !active[channel] {
			continue
		}
		complete, e := s.deliver(event)
		if e != nil {
			pushError(run, D{"event": at(event, "_id"), "error_type": safe(e).Kind})
		} else if complete {
			bump(run, "completed")
		}
	}
	events, e = s.App.DB.find("settings", filter, nil, 0, nil)
	if e != nil {
		return e
	}
	for _, event := range events {
		bump(run, "pending")
		deliveries, ok := at(event, "deliveries").([]any)
		if !ok {
			return fault("Config")
		}
		for _, part := range deliveries {
			state := field(part, "state")
			if state == "sending" || state == "uncertain" {
				bump(run, "uncertain_messages")
			}
		}
	}
	status := "success"
	if num(at(run, "pending"), 0) > 0 || len(arr(at(run, "errors"))) > 0 {
		status = "partial"
	}
	run["status"] = status
	return nil
}
func anniversaries(app *App, sender *Sender) (Supply, error) {
	service := &Anniversary{App: app, Sender: sender, Lease: newLease(app.DB, "r2t_anniversary_sweep_lock")}
	id := anniversaryRunKind + ":" + uuid()
	run := D{"_id": id, "kind": anniversaryRunKind, "setting": id, "owner": service.Lease.Owner,
		"date": timeText(now(), "2006-01-02", true), "started_at": date(now()), "status": "running", "channels": 0, "due": 0, "completed": 0,
		"pending": 0, "uncertain_messages": 0, "skipped_no_history": A{}, "errors": A{}}
	if e := app.DB.insert("settings", A{run}); e != nil {
		return Skip, e
	}
	acquired := false
	outcome := func() (e error) {
		defer func() {
			if recover() != nil {
				e = fault("NativeError")
			}
		}()
		return service.sweep(run, &acquired)
	}()
	if outcome != nil {
		run["status"] = "failed"
		pushError(run, D{"error_type": safe(outcome).Kind})
	}
	run["finished_at"] = date(now())
	values := doc(clone(run))
	delete(values, "_id")
	if _, e := app.DB.update("settings", D{"_id": id}, D{"$set": values}, false, false); e != nil && outcome == nil {
		outcome = e
	}
	if acquired {
		if e := service.Lease.release(); e != nil && outcome == nil {
			outcome = e
		}
	}
	if outcome != nil {
		return Skip, outcome
	}
	if field(run, "status") == "failed" || field(run, "status") == "partial" {
		return Skip, fault("Announcement")
	}
	return Stop, nil
}
