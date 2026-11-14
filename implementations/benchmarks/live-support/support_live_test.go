package main

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"testing"
)

const liveTarget = "@r_channels_test"

var liveChatID int64
var liveCalls = D{}
var liveDatabase string

// This is inserted at the Telegram API boundary in the staged test package.
// No getUpdates, arbitrary destinations, media uploads or unknown methods.
func liveRequestGuard(method string, params D, video string) error {
	if os.Getenv("R2T_LIVE_TESTS") != "1" || mainChannel != liveTarget || community != liveTarget || video != "" {
		return fault("LiveGuard")
	}
	allowed := func(v any) bool {
		if s, ok := v.(string); ok && strings.EqualFold(s, liveTarget) {
			return true
		}
		n, e := whole(v)
		if s, ok := v.(string); ok {
			n, e = strconv.ParseInt(s, 10, 64)
		}
		return e == nil && liveChatID < 0 && n == liveChatID
	}
	switch method {
	case "getChat", "getChatMemberCount", "getChatAdministrators", "sendMessage":
		if !allowed(at(params, "chat_id")) {
			return fault("LiveGuard")
		}
	case "forwardMessage":
		if !allowed(at(params, "chat_id")) || !allowed(at(params, "from_chat_id")) {
			return fault("LiveGuard")
		}
	default:
		return fault("LiveGuard")
	}
	liveCalls[method] = int64(num(at(liveCalls, method), 0)) + 1
	return nil
}

func liveMust(t *testing.T, e error) {
	t.Helper()
	if e != nil {
		f := safe(e)
		t.Fatalf("operation failed: %s code=%d", f.Kind, f.Code)
	}
}

func liveRow(t *testing.T, db *Database, id any) D {
	t.Helper()
	row, e := db.one("settings", D{"_id": id}, nil)
	liveMust(t, e)
	if row == nil {
		t.Fatal("missing persisted event")
	}
	return row
}

func liveCase(t *testing.T, name string, body func(*testing.T, D)) {
	t.Helper()
	t.Run(name, func(t *testing.T) {
		started := now()
		before := doc(clone(liveCalls))
		info := D{"case": name, "started_at": started, "isolated_database": liveDatabase, "source_commit": liveSourceRevision}
		defer func() {
			info["ended_at"] = now()
			info["passed"] = !t.Failed()
			delta := D{}
			for method, value := range liveCalls {
				delta[method] = num(value, 0) - num(at(before, method), 0)
			}
			info["api_attempts"] = delta
			path := os.Getenv("R2T_LIVE_RECEIPTS")
			f, e := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0600)
			liveMust(t, e)
			defer f.Close()
			_, e = f.WriteString(dump(info) + "\n")
			liveMust(t, e)
		}()
		body(t, info)
	})
}

func TestLiveSupport(t *testing.T) {
	if os.Getenv("R2T_LIVE_TESTS") != "1" {
		t.Skip("local opt-in live support checks")
	}
	if mainChannel != liveTarget || community != liveTarget {
		t.Fatal("requires test-only routed package")
	}
	configPath, receipts := os.Getenv("R2T_LIVE_CONFIG"), os.Getenv("R2T_LIVE_RECEIPTS")
	if !filepath.IsAbs(configPath) || !filepath.IsAbs(receipts) {
		t.Fatal("absolute local config and receipt paths required")
	}
	config, e := loadConfig(configPath)
	liveMust(t, e)
	productionName := field(at(config.Values, "db"), "name")
	name := "r2t_live_support_" + uuid()
	if name == productionName || !strings.HasPrefix(name, "r2t_live_support_") {
		t.Fatal("isolated database required")
	}
	liveDatabase = name
	redditConfig := clone(at(config.Values, "reddit"))
	config.Values = D{"db": D{"host": at(at(config.Values, "db"), "host"), "name": name},
		"telegram": D{"token": at(at(config.Values, "telegram"), "token"), "dev_chat": liveTarget}, "reddit": redditConfig}
	config.Root = t.TempDir()
	config.App = config.Root
	cron := filepath.Join(config.Root, "support.cron")
	config.Values["cron_file"] = cron
	liveMust(t, os.WriteFile(cron, []byte("schedule\tmodule\n* * * * *\tlive_support\n"), 0600))
	db, e := newDatabase(config)
	liveMust(t, e)
	defer db.close() // Isolated evidence retained; no drop/reset of any database.
	app := &App{Config: config, DB: db, Videos: make(chan struct{}, 2)}
	sender := app.sender(liveTarget, nil)
	defer sender.close()
	chat, e := sender.api("getChat", D{"chat_id": liveTarget})
	liveMust(t, e)
	liveChatID, e = whole(at(chat, "id"))
	liveMust(t, e)
	if liveChatID >= 0 || !strings.EqualFold(field(chat, "username"), strings.TrimPrefix(liveTarget, "@")) {
		t.Fatal("test channel identity mismatch")
	}
	liveMust(t, db.insert("channels", A{D{"submodule": "live_support", "channel": "@R_CHANNELS_TEST", "subreddit": "aww", "anniversary_date": "2020-11-12"}}))
	lease := newLease(db, "live_support_lease")
	acquired, e := lease.acquire()
	liveMust(t, e)
	if !acquired {
		t.Fatal("lease acquisition failed")
	}
	defer func() { liveMust(t, lease.release()) }()

	liveCase(t, "receiver_index_conflict", func(t *testing.T, info D) {
		_, e := db.command("createIndexes", "settings", D{"indexes": A{D{"key": D{"setting": 1}, "name": "setting_1"}}})
		liveMust(t, e)
		_, e = receiver(app, sender)
		f := safe(e)
		info["error_kind"], info["mongo_error_code"] = f.Kind, f.Code
		if f.Kind != "Database" || (f.Code != 85 && f.Code != 86) {
			t.Fatalf("expected isolated index conflict, got %s code=%d", f.Kind, f.Code)
		}
	})
	liveCase(t, "anniversary_delivery_and_yearly_dedup", func(t *testing.T, info D) {
		s := &Anniversary{App: app, Sender: sender, Lease: lease}
		birthday, found, e := s.birthday(liveTarget, D{"anniversary_date": "2020-11-12"})
		liveMust(t, e)
		if !found || timeText(birthday, "2006-01-02", true) != "2020-11-12" {
			t.Fatal("explicit birthday not cached")
		}
		cached, found, e := s.birthday(liveTarget, D{})
		liveMust(t, e)
		if !found || cached != birthday {
			t.Fatal("cached birthday changed")
		}
		today, e := midnight(timeText(now(), "2006-01-02", true))
		liveMust(t, e)
		liveMust(t, s.queue(liveTarget, 6, today, []string{liveTarget}))
		id := fmt.Sprintf("%s:%s:%d", anniversaryEventKind, liveTarget, parts(today, true).Year())
		complete, e := s.deliver(liveRow(t, db, id))
		liveMust(t, e)
		if !complete {
			t.Fatal("anniversary incomplete")
		}
		row := liveRow(t, db, id)
		parts := arr(at(row, "deliveries"))
		if len(parts) != 1 || field(parts[0], "state") != "sent" || len(arr(at(parts[0], "message_ids"))) == 0 {
			t.Fatal("acknowledgement not persisted")
		}
		checkpoint := dump(row)
		sentBefore := num(at(liveCalls, "sendMessage"), 0)
		liveMust(t, s.queue(liveTarget, 6, today, []string{liveTarget}))
		complete, e = s.deliver(liveRow(t, db, id))
		liveMust(t, e)
		if !complete || sentBefore != num(at(liveCalls, "sendMessage"), 0) {
			t.Fatal("duplicate send on resume")
		}
		after := liveRow(t, db, id)
		if dump(at(after, "deliveries")) != dump(at(row, "deliveries")) {
			t.Fatal("delivery checkpoint changed")
		}
		info["acknowledged_parts"], info["duplicate_resends"] = len(parts), 0
		info["checkpoint_sha256"] = digest([]byte(checkpoint))
	})
	liveCase(t, "anniversary_uncertainty_hold", func(t *testing.T, info D) {
		id := "controlled_uncertainty"
		liveMust(t, db.insert("settings", A{D{"_id": id, "kind": anniversaryEventKind, "complete": false, "deliveries": A{D{"destination": liveTarget, "text": "must remain held", "state": "sending"}, D{"destination": liveTarget, "text": "must remain blocked", "state": "pending"}}}}))
		before := num(at(liveCalls, "sendMessage"), 0)
		complete, e := (&Anniversary{App: app, Sender: sender, Lease: lease}).deliver(liveRow(t, db, id))
		liveMust(t, e)
		row := liveRow(t, db, id)
		parts := arr(at(row, "deliveries"))
		if complete || field(parts[0], "state") != "uncertain" || field(parts[1], "state") != "pending" || before != num(at(liveCalls, "sendMessage"), 0) {
			t.Fatal("uncertainty safeguards changed")
		}
		info["held_uncertain_parts"], info["blocked_pending_parts"], info["resends"] = 1, 1, 0
	})
	liveCase(t, "milestone_crossing_delivery_and_resume", func(t *testing.T, info D) {
		s := &Milestones{App: app, Sender: sender, Lease: lease}
		value, e := sender.api("getChatMemberCount", D{})
		liveMust(t, e)
		members, e := whole(value)
		liveMust(t, e)
		if members < 1 {
			t.Fatal("test channel has no members")
		}
		liveMust(t, db.insert("stats", A{D{"channel": liveTarget, "ts": date(now() - 60), "members_cnt": members - 1}}))
		totals, snapshots := &Totals{}, []Snapshot{}
		// Controlled prior value and threshold; current count is a real API value.
		// Missing module deliberately takes the supported text fallback before Reddit.
		liveMust(t, s.collectMembers("controlled_missing_source", liveTarget, D{"channel": liveTarget, "ts": date(now())}, totals, A{members}, &snapshots))
		id := fmt.Sprintf("%s:%s:%d", achievementEventKind, liveTarget, members)
		liveMust(t, s.deliver(liveRow(t, db, id)))
		row := liveRow(t, db, id)
		if at(row, "complete") != true || len(arr(at(row, "message_ids"))) == 0 {
			t.Fatal("milestone checkpoint incomplete")
		}
		before := num(at(liveCalls, "sendMessage"), 0)
		liveMust(t, s.queue("controlled_missing_source", liveTarget, members))
		pending, e := db.count("settings", D{"kind": achievementEventKind, "complete": false})
		liveMust(t, e)
		if pending != 0 || before != num(at(liveCalls, "sendMessage"), 0) {
			t.Fatal("milestone dedup failed")
		}
		// Resume a recorded source acknowledgement and forward within the SAME test channel.
		resumeID := "controlled_forward_resume"
		liveMust(t, db.insert("settings", A{D{"_id": resumeID, "channel": strconv.FormatInt(liveChatID, 10), "achievement": members, "message_ids": at(row, "message_ids"), "forwarded_ids": A{}, "complete": false}}))
		liveMust(t, s.deliver(liveRow(t, db, resumeID)))
		forwarded := liveRow(t, db, resumeID)
		if len(arr(at(forwarded, "forwarded_ids"))) == 0 || at(forwarded, "complete") != true {
			t.Fatal("forward checkpoint missing")
		}
		forwardBefore := num(at(liveCalls, "forwardMessage"), 0)
		liveMust(t, s.deliver(forwarded))
		if before != num(at(liveCalls, "sendMessage"), 0) || forwardBefore != num(at(liveCalls, "forwardMessage"), 0) {
			t.Fatal("resume duplicated acknowledged delivery")
		}
		info["current_count_source"], info["controlled_crossing"], info["fallback_acknowledged"], info["forward_acknowledged"], info["duplicate_resends"] = "live Telegram API", true, true, true, 0
	})
	liveCase(t, "weekly_report_delivery", func(t *testing.T, info D) {
		liveMust(t, db.insert("urls", A{D{"channel": liveTarget, "ts": date(now() - 86400), "sent": true}}))
		liveMust(t, db.insert("stats", A{D{"channel": liveTarget, "ts": date(now() - 2*86400), "members_cnt": int64(1)}, D{"channel": liveTarget, "ts": date(now() + 1), "members_cnt": int64(100)}}))
		ids := A{}
		sender.Ack = func(values A) error { ids = append(ids, values...); return nil }
		defer func() { sender.Ack = nil }()
		result, e := weekly(app, sender)
		liveMust(t, e)
		if result != Stop || len(ids) != 2 {
			t.Fatal("weekly summary/directory acknowledgements missing")
		}
		info["acknowledged_messages"], info["input_scope"] = len(ids), "controlled isolated statistics; real Telegram delivery"
	})
	liveCase(t, "receiver_channel_intake_delivery", func(t *testing.T, info D) {
		for _, input := range []string{"/newchannel", "aww", liveTarget, "#live #support"} {
			liveMust(t, processMessage(app, sender, liveChatID, input))
		}
		record, e := db.one("channels", D{"submodule": "r_channels_test"}, nil)
		liveMust(t, e)
		if field(record, "channel") != liveTarget || field(record, "subreddit") != "aww" {
			t.Fatal("intake record missing")
		}
		pending, e := db.count("settings", D{"setting": fmt.Sprintf("tech_receiver_state:%d", liveChatID)})
		liveMust(t, e)
		if pending != 0 {
			t.Fatal("intake draft not cleared")
		}
		info["persisted"], info["polling_scope"] = true, "direct controlled intake; production getUpdates excluded"
	})
	liveCase(t, "cleaner_isolated_files_and_tasks", func(t *testing.T, info D) {
		tmp := filepath.Join(config.App, "tmp")
		liveMust(t, os.Mkdir(tmp, 0700))
		liveMust(t, os.WriteFile(filepath.Join(tmp, "controlled-test-file"), []byte("live cleanup fixture"), 0600))
		for status := 1; status <= 5; status++ {
			liveMust(t, db.insert("tasks", A{D{"status": status}}))
		}
		result, e := cleaner(app, sender)
		liveMust(t, e)
		if result != Stop {
			t.Fatal("cleaner did not finish")
		}
		if _, e := os.Stat(filepath.Join(tmp, "controlled-test-file")); !os.IsNotExist(e) {
			t.Fatal("fixture file not cleaned")
		}
		count, e := db.count("tasks", D{})
		liveMust(t, e)
		if count != 0 {
			t.Fatal("isolated task cleanup incomplete")
		}
		info["fixture_tasks_deleted"], info["scope"] = 5, "isolated temporary directory and database; real test-channel report"
	})
	liveCase(t, "milestone_live_reddit_candidate", func(t *testing.T, info D) {
		// Query current Reddit listings and deliver a selected post through the
		// actual announcement path. Only the test channel can pass the API guard.
		_, e := db.update("channels", D{"submodule": "live_support"}, D{"$set": D{"subreddit": "Showerthoughts", "tags": "#live #support #candidate"}}, false, false)
		liveMust(t, e)
		s := &Milestones{App: app, Sender: sender, Lease: lease}
		liveMust(t, s.queue("live_support", liveTarget, 500))
		id := fmt.Sprintf("%s:%s:%d", achievementEventKind, liveTarget, 500)
		row := liveRow(t, db, id)
		checkpoint := newCheckpoint(db, D{"_id": id}, "", nil)
		attempted := false
		e = s.candidate(row, checkpoint, &attempted)
		if e != nil {
			info["error_kind"], info["error_code"] = safe(e).Kind, safe(e).Code
		}
		liveMust(t, e)
		if !attempted || len(checkpoint.ids()) == 0 {
			t.Fatal("no live Reddit candidate acknowledged; fallback is excluded in this case")
		}
		liveMust(t, s.deliver(liveRow(t, db, id)))
		event := liveRow(t, db, id)
		posts, e := db.count("urls", D{"channel": liveTarget, "sent": true})
		liveMust(t, e)
		if at(event, "complete") != true || posts == 0 || len(arr(at(event, "message_ids"))) == 0 {
			t.Fatal("candidate delivery/post checkpoints missing")
		}
		info["selected_live_reddit_candidate"], info["acknowledged_parts"], info["controlled_threshold"], info["posts_recorded_sent"] = true, len(checkpoint.ids()), 500, posts
	})
	liveCase(t, "anniversary_live_directory_delivery_resume", func(t *testing.T, info D) {
		path := os.Getenv("R2T_LIVE_DIRECTORY")
		if !filepath.IsAbs(path) {
			t.Fatal("absolute live directory snapshot path required")
		}
		raw, e := os.ReadFile(path)
		liveMust(t, e)
		value, e := parse(raw)
		liveMust(t, e)
		channels := []string{}
		valid := regexp.MustCompile(`^@[A-Za-z][A-Za-z0-9_]{4,31}$`)
		for _, item := range arr(at(value, "channels")) {
			channel, ok := item.(string)
			if !ok || !valid.MatchString(channel) {
				t.Fatal("invalid directory handle")
			}
			channels = append(channels, channel)
		}
		if len(channels) < 101 {
			t.Fatal("live directory does not exercise pagination")
		}
		caseConfig := *config
		caseConfig.Values = doc(clone(config.Values))
		caseConfig.Values["db"] = D{"host": at(at(config.Values, "db"), "host"), "name": "r2t_live_support_directory_" + uuid()}
		caseDB, e := newDatabase(&caseConfig)
		liveMust(t, e)
		defer caseDB.close()
		caseLease := newLease(caseDB, "directory_live_lease")
		acquired, e := caseLease.acquire()
		liveMust(t, e)
		if !acquired {
			t.Fatal("directory lease not acquired")
		}
		defer func() { liveMust(t, caseLease.release()) }()
		caseApp := &App{Config: &caseConfig, DB: caseDB, Videos: app.Videos}
		caseSender := caseApp.sender(liveTarget, nil)
		defer caseSender.close()
		info["isolated_database"] = caseDB.Name
		s := &Anniversary{App: caseApp, Sender: caseSender, Lease: caseLease}
		today, e := midnight(timeText(now(), "2006-01-02", true))
		liveMust(t, e)
		liveMust(t, s.queue(liveTarget, 6, today, channels))
		id := fmt.Sprintf("%s:%s:%d", anniversaryEventKind, liveTarget, parts(today, true).Year())
		queued := liveRow(t, caseDB, id)
		if len(arr(at(queued, "deliveries"))) < 3 {
			t.Fatal("expected introduction and multiple directory pages")
		}
		complete, e := s.deliver(queued)
		liveMust(t, e)
		if !complete {
			t.Fatal("paged anniversary delivery incomplete")
		}
		row := liveRow(t, caseDB, id)
		deliveries := arr(at(row, "deliveries"))
		for _, part := range deliveries {
			if field(part, "state") != "sent" || len(arr(at(part, "message_ids"))) == 0 {
				t.Fatal("page checkpoint not persisted")
			}
		}
		before := num(at(liveCalls, "sendMessage"), 0)
		complete, e = s.deliver(row)
		liveMust(t, e)
		if !complete || before != num(at(liveCalls, "sendMessage"), 0) {
			t.Fatal("resume duplicated an acknowledged page")
		}
		if dump(at(liveRow(t, caseDB, id), "deliveries")) != dump(at(row, "deliveries")) {
			t.Fatal("page checkpoint changed on resume")
		}
		info["directory_channels"], info["directory_snapshot_sha256"], info["acknowledged_parts"], info["duplicate_resends"] = len(channels), digest(raw), len(deliveries), 0
	})
	t.Logf("isolated database evidence retained; source=%s", liveSourceRevision)
}
