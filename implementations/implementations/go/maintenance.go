package main

import (
	"fmt"
	"math"
	"os"
	"os/exec"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"syscall"
)

func cleaner(app *App, sender *Sender) (Supply, error) {
	raw, e := os.ReadFile("/proc/meminfo")
	if e != nil {
		return Skip, fault("Io")
	}
	free := -1.0
	for _, line := range strings.Split(string(raw), "\n") {
		if strings.HasPrefix(line, "MemFree:") {
			values := words(line)
			if len(values) > 1 {
				n, err := strconv.ParseFloat(values[1], 64)
				if err == nil {
					free = n / 1024
				}
			}
		}
	}
	if free < 0 {
		return Skip, fault("Io")
	}
	deleted, e := cleanFiles(app.Config, nil)
	if e != nil {
		return Skip, e
	}
	var disk syscall.Statfs_t
	if syscall.Statfs("/", &disk) != nil {
		return Skip, fault("Io")
	}
	output, e := exec.Command("vnstat", "-m").Output()
	if e != nil {
		return Skip, fault("Io")
	}
	lines := strings.Split(string(output), "\n")
	if len(lines) < 4 {
		return Skip, fault("Io")
	}
	trafficParts := strings.Split(lines[len(lines)-4], " | ")
	estimateParts := strings.Split(lines[len(lines)-2], "|")
	if len(trafficParts) < 2 || len(estimateParts) < 2 {
		return Skip, fault("Io")
	}
	traffic, estimate := trimSpace(trafficParts[len(trafficParts)-2]), trimSpace(estimateParts[len(estimateParts)-2])
	aggregate, e := app.DB.command("aggregate", "tasks", D{"pipeline": A{D{"$group": D{"_id": "$status", "count": D{"$sum": 1}}}}, "cursor": D{}})
	if e != nil {
		return Skip, e
	}
	counts := map[int64]int64{}
	for _, record := range arr(at(at(aggregate, "cursor"), "firstBatch")) {
		id, e := whole(at(record, "_id"))
		if e == nil {
			counts[id] = int64(num(at(record, "count"), 0))
		}
	}
	previous, e := app.DB.one("settings", D{"setting": "tasks-stati"}, nil)
	if e != nil {
		return Skip, e
	}
	data := doc(clone(at(previous, "data")))
	cycles := int64(0)
	for _, value := range data {
		cycles = max(cycles, int64(num(at(value, "cycles_cnt"), 0)))
	}
	cycles++
	body := fmt.Sprintf("Free memory: %.3fMB.\nDeleted files: %.3fGB.\nAvailable disk space: %.3fGB.\nCurrent month traffic: %s.\nCurrent month estimate: %s.\nTasks' stati:\n", free, float64(deleted)/math.Pow(1024, 3), float64(disk.Bavail)*float64(disk.Bsize)/math.Pow(1024, 3), traffic, estimate)
	names := []string{"", "NEW", "IN_PROGRESS", "SUCCESS", "FAILED", "SCHEDULED"}
	removed := int64(0)
	for status := int64(1); status <= 5; status++ {
		name := names[status]
		old := at(data, name)
		total := int64(num(at(old, "amt"), 0)) + counts[status]
		data[name] = D{"amt": total, "cycles_cnt": int64(num(at(old, "cycles_cnt"), 0)) + 1}
		body += fmt.Sprintf("  →  %s: %d (avg: %.3f)\n", name, counts[status], float64(total)/float64(cycles))
		n, e := app.DB.remove("tasks", D{"status": status}, false)
		if e != nil {
			return Skip, e
		}
		removed += n
	}
	body += fmt.Sprintf("Deleted tasks: %d.\nTotal cycles: %d.\n", removed, cycles)
	if _, e = app.DB.update("settings", D{"setting": "tasks-stati"}, D{"$set": D{"data": data}}, false, true); e != nil {
		return Skip, e
	}
	if _, e = sender.text(body, false, ""); e != nil {
		return Skip, e
	}
	return Stop, nil
}
func publicChannels(app *App, sender *Sender) ([]string, error) {
	modules, e := app.publicModules()
	if e != nil {
		return nil, e
	}
	unique := map[string]float64{}
	for _, module := range modules {
		destination, _, e := app.identity(module)
		if e != nil {
			return nil, e
		}
		channel, ok := destination.(string)
		if !ok {
			return nil, fault("Config")
		}
		if !strings.Contains(channel, "@") || channel == "@r_channels" || channel == "@r_channels_test" {
			continue
		}
		first, e := sender.DB.one("urls", D{"channel": lower(channel)}, D{"ts": 1})
		if e != nil {
			return nil, e
		}
		stamp, ok := timestamp(at(first, "ts"))
		if !ok {
			return nil, fault("Config")
		}
		unique[channel] = stamp
	}
	channels := []string{}
	for channel := range unique {
		channels = append(channels, channel)
	}
	sort.Strings(channels)
	sort.SliceStable(channels, func(i, j int) bool { return unique[channels[i]] < unique[channels[j]] })
	return channels, nil
}
func firstMembers(app *App, filter, sort D) (float64, error) {
	records, e := app.DB.find("stats", filter, sort, 100, nil)
	if e != nil {
		return 0, e
	}
	for _, record := range records {
		if numeric(at(record, "members_cnt")) {
			return num(at(record, "members_cnt"), 0), nil
		}
	}
	return 0, fault("Config")
}
func weekly(app *App, sender *Sender) (Supply, error) {
	channels, e := publicChannels(app, sender)
	if e != nil {
		return Skip, e
	}
	newly := []string{}
	type growth struct {
		channel string
		delta   float64
	}
	growing := []growth{}
	cutoff := date(now() - 7*86400)
	for _, channel := range channels {
		filter := D{"channel": lower(channel)}
		first, e := app.DB.one("stats", filter, D{"ts": 1})
		if e != nil {
			return Skip, e
		}
		last, e := app.DB.one("stats", filter, D{"ts": -1})
		if e != nil {
			return Skip, e
		}
		a, ok := timestamp(at(first, "ts"))
		if !ok {
			return Skip, fault("Config")
		}
		b, ok := timestamp(at(last, "ts"))
		if !ok {
			return Skip, fault("Config")
		}
		if math.Floor((b-a)/86400) <= 31 {
			newly = append(newly, channel)
		}
		previous, e := firstMembers(app, D{"channel": lower(channel), "ts": D{"$gte": cutoff}}, D{"ts": 1})
		if e != nil {
			return Skip, e
		}
		current, e := firstMembers(app, filter, D{"ts": -1})
		if e != nil {
			return Skip, e
		}
		if current-previous >= 10 {
			growing = append(growing, growth{channel, current - previous})
		}
	}
	if len(channels) == 0 {
		return Skip, fault("Config")
	}
	sort.SliceStable(growing, func(i, j int) bool { return growing[i].delta > growing[j].delta })
	body := "<b>Weekend news</b>\n\n"
	if len(newly) > 0 {
		body += "🎉 Welcome to newly active channels: " + strings.Join(newly, ", ") + ". 🎈🎈\n\n"
	}
	body += "🏆 Channel of the week: " + channels[randomIndex(len(channels))] + ". Join and enjoy!\n\n"
	if len(growing) > 0 {
		top := []string{}
		for _, row := range growing[:min(3, len(growing))] {
			top = append(top, row.channel)
		}
		body += "🔥 Hottest channels of the week: " + strings.Join(top, ", ") + ".\n\n"
	}
	body += "🙋\nQ: How can I help?\nA: Support us on Patreon and promote your favorite channels!\n\nQ: How to make similar channels?\nA: Ask at @r_channels or use manual at https://github.com/Fillll/reddit2telegram.\n\nQ: Where to donate?\nA: Patreon: https://www.patreon.com/reddit2telegram."
	if _, e = sender.text(body, false, "HTML"); e != nil {
		return Skip, e
	}
	pause(2, 2)
	for index := 0; index < len(channels); index += 100 {
		body = ""
		if index == 0 {
			body = "⬇️ All active channels:\n"
		}
		rows := []string{}
		for i := index; i < min(index+100, len(channels)); i++ {
			rows = append(rows, fmt.Sprintf("%02d. %s", i+1, channels[i]))
		}
		if _, e = sender.text(body+strings.Join(rows, "\n"), false, ""); e != nil {
			return Skip, e
		}
		pause(2, 2)
	}
	return Stop, nil
}

const receiverHelp = "Send channel data in one message:\nsubreddit: https://reddit.com/r/example\nchannel: @example_channel\ntags: #tag1 #tag2 #tag3\n\nOr send it step by step:\n1. subreddit\n2. channel\n3. tags\n\nCommands:\n/newchannel to restart\n/cancel to clear the current draft"

func normalizeName(input, kind string) string {
	prefix := regexp.MustCompile(`(?i)^[` + spaceCharacters + `]*` + kind + `[` + spaceCharacters + `]*:[` + spaceCharacters + `]*`)
	value := prefix.ReplaceAllString(trimSpace(input), "")
	pattern := `(?i)(?:https?://)?(?:www\.)?reddit\.com/r/([^/?#` + spaceCharacters + `]+)`
	if kind != "subreddit" {
		pattern = `(?i)(?:https?://)?(?:t(?:elegram)?\.me/)([^/?#` + spaceCharacters + `]+)`
	}
	if match := regexp.MustCompile(pattern).FindStringSubmatch(value); len(match) > 1 {
		value = match[1]
	} else {
		value = strings.Trim(trimSpace(value), "/")
	}
	if kind == "subreddit" && strings.HasPrefix(lower(value), "r/") {
		value = value[2:]
	}
	if kind == "channel" {
		value = strings.TrimPrefix(value, "@")
	}
	if value == "" || len(words(value)) != 1 {
		return ""
	}
	return strings.Trim(trimSpace(value), "/")
}
func normalizeTags(input string) string {
	value := regexp.MustCompile(`(?i)^[`+spaceCharacters+`]*tags[`+spaceCharacters+`]*:[`+spaceCharacters+`]*`).ReplaceAllString(trimSpace(input), "")
	value = strings.ReplaceAll(value, ",", " ")
	seen := map[string]bool{}
	tags := []string{}
	for _, part := range words(value) {
		if !strings.HasPrefix(part, "#") {
			part = "#" + part
		}
		if !seen[part] {
			tags = append(tags, part)
			seen[part] = true
		}
	}
	return strings.Join(tags, " ")
}
func completeData(data D) bool {
	return field(data, "subreddit") != "" && field(data, "channel") != "" && field(data, "tags") != ""
}
func completeRequest(input string) D {
	lines := []string{}
	for _, line := range strings.Split(input, "\n") {
		line = trimSpace(line)
		if line != "" {
			lines = append(lines, line)
		}
	}
	if len(lines) > 0 && (lower(lines[0]) == "/newchannel" || lower(lines[0]) == "/start") {
		lines = lines[1:]
	}
	data := D{}
	for _, line := range lines {
		low := lower(line)
		if strings.HasPrefix(low, "subreddit") {
			data["subreddit"] = normalizeName(line, "subreddit")
		} else if strings.HasPrefix(low, "channel") {
			data["channel"] = normalizeName(line, "channel")
		} else if strings.HasPrefix(low, "tags") {
			data["tags"] = normalizeTags(line)
		}
	}
	if completeData(data) {
		return data
	}
	if len(lines) == 3 {
		data = D{"subreddit": normalizeName(lines[0], "subreddit"), "channel": normalizeName(lines[1], "channel"), "tags": normalizeTags(lines[2])}
		if completeData(data) {
			return data
		}
	}
	return nil
}
func reply(app *App, source *Sender, user int64, body string) error {
	sender := app.sender(user, source.Metrics)
	defer sender.close()
	_, e := sender.text(body, false, "")
	return e
}
func saveChannel(app *App, source *Sender, user int64, data D) error {
	channel, subreddit, tags := field(data, "channel"), field(data, "subreddit"), field(data, "tags")
	filter := D{"submodule": lower(channel)}
	existing, e := app.DB.one("channels", filter, nil)
	if e != nil {
		return e
	}
	if _, e = app.DB.update("channels", filter, D{"$set": D{"submodule": lower(channel), "channel": "@" + channel, "subreddit": subreddit, "tags": tags, "min_upvotes_limit": nil, "submissions_ranking": "hot", "submissions_limit": 100}}, false, true); e != nil {
		return e
	}
	if _, e = app.DB.remove("settings", D{"setting": fmt.Sprintf("tech_receiver_state:%d", user)}, true); e != nil {
		return e
	}
	action := "Saved"
	if existing != nil {
		action = "Updated"
	}
	return reply(app, source, user, fmt.Sprintf("%s channel:\nsubreddit: r/%s\nchannel: @%s\ntags: %s", action, subreddit, channel, tags))
}
func processMessage(app *App, sender *Sender, user int64, input string) error {
	filter := D{"setting": fmt.Sprintf("tech_receiver_state:%d", user)}
	low := lower(trimSpace(input))
	if low == "/help" || low == "help" {
		return reply(app, sender, user, receiverHelp)
	}
	if low == "/cancel" || low == "cancel" {
		if _, e := app.DB.remove("settings", filter, true); e != nil {
			return e
		}
		return reply(app, sender, user, "Draft cleared.")
	}
	if low == "/newchannel" || low == "/start" {
		if _, e := app.DB.remove("settings", filter, true); e != nil {
			return e
		}
		if _, e := app.DB.update("settings", filter, D{"$set": D{"data": D{"step": "await_subreddit"}}}, false, true); e != nil {
			return e
		}
		return reply(app, sender, user, "Send subreddit name or Reddit URL.")
	}
	if data := completeRequest(input); data != nil {
		return saveChannel(app, sender, user, data)
	}
	previous, e := app.DB.one("settings", filter, nil)
	if e != nil {
		return e
	}
	state := D{"step": "await_subreddit"}
	if previous != nil {
		state = doc(clone(at(previous, "data")))
	}
	response := ""
	switch field(state, "step") {
	case "await_subreddit":
		value := normalizeName(input, "subreddit")
		if value == "" {
			return reply(app, sender, user, receiverHelp)
		}
		state = D{"step": "await_channel", "subreddit": value}
		response = "Saved subreddit: r/" + value + "\nNow send channel (@name or t.me link)."
	case "await_channel":
		value := normalizeName(input, "channel")
		if value == "" {
			return reply(app, sender, user, "Channel is invalid. Send @channel_name or https://t.me/channel_name")
		}
		state["step"] = "await_tags"
		state["channel"] = value
		response = "Saved channel: @" + value + "\nNow send tags like #tag1 #tag2 #tag3"
	case "await_tags":
		tags := normalizeTags(input)
		if tags == "" {
			return reply(app, sender, user, "Tags are invalid. Send tags like #tag1 #tag2 #tag3")
		}
		if _, ok := at(state, "channel").(string); !ok {
			return fault("Config")
		}
		if _, ok := at(state, "subreddit").(string); !ok {
			return fault("Config")
		}
		return saveChannel(app, sender, user, D{"channel": at(state, "channel"), "subreddit": at(state, "subreddit"), "tags": tags})
	default:
		if _, e = app.DB.remove("settings", filter, true); e != nil {
			return e
		}
		return reply(app, sender, user, receiverHelp)
	}
	if _, e = app.DB.update("settings", filter, D{"$set": D{"data": state}}, false, true); e != nil {
		return e
	}
	return reply(app, sender, user, response)
}
func receiver(app *App, sender *Sender) (Supply, error) {
	if _, e := app.DB.command("createIndexes", "settings", D{"indexes": A{D{"key": D{"setting": 1}, "name": "setting_1", "unique": true}}}); e != nil {
		return Skip, e
	}
	filter := D{"setting": 1}
	record, e := app.DB.one("settings", filter, nil)
	if e != nil {
		return Skip, e
	}
	last := int64(0)
	if record == nil {
		if e = app.DB.insert("settings", A{D{"setting": 1, "last_update": 0}}); e != nil {
			return Skip, e
		}
	} else {
		last, e = whole(at(record, "last_update"))
		if e != nil {
			return Skip, e
		}
	}
	updates, e := sender.api("getUpdates", D{"offset": last + 1})
	if e != nil {
		return Skip, e
	}
	items, ok := updates.([]any)
	if !ok {
		return Skip, fault("Telegram")
	}
	configured := at(at(app.Config.Values, "telegram"), "papa")
	papa, e := whole(configured)
	if e != nil {
		value, err := strconv.ParseInt(str(configured), 10, 64)
		if err != nil {
			return Skip, fault("Config")
		}
		papa = value
	}
	for _, update := range items {
		id, e := whole(at(update, "update_id"))
		if e != nil {
			return Skip, fault("Telegram")
		}
		last = max(last, id)
		message := at(update, "message")
		user, e := whole(at(at(message, "chat"), "id"))
		if e != nil || user < 0 {
			continue
		}
		body, ok := at(message, "text").(string)
		if !ok {
			continue
		}
		if _, e = sender.api("forwardMessage", D{"chat_id": at(at(app.Config.Values, "telegram"), "dev_chat"), "from_chat_id": user, "message_id": at(message, "message_id")}); e != nil {
			return Skip, e
		}
		if user == papa {
			if e = processMessage(app, sender, user, body); e != nil {
				return Skip, e
			}
		}
	}
	if _, e = app.DB.update("settings", filter, D{"$set": D{"last_update": last}}, false, false); e != nil {
		return Skip, e
	}
	return Stop, nil
}
