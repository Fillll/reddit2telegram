package main

import (
	"math"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"sync"
)

type Channel struct {
	Destination        any
	Options            D
	Subreddit, Ranking string
	Limit              int
	RequiresSubmission bool
}

var channelCache struct {
	weightedMu, promotionMu sync.Mutex
	weighted, promotion     string
}

func (a *App) publicModules() ([]string, error) {
	rows, e := schedules(a.Config)
	if e != nil {
		return nil, e
	}
	unique := map[string]bool{}
	for _, row := range rows {
		if !strings.HasPrefix(row.Module, "tech_") {
			unique[row.Module] = true
		}
	}
	names := make([]string, 0, len(unique))
	for name := range unique {
		names = append(names, name)
	}
	sort.Strings(names)
	return names, nil
}
func weightedSource() (string, error) {
	channelCache.weightedMu.Lock()
	defer channelCache.weightedMu.Unlock()
	if channelCache.weighted != "" {
		return channelCache.weighted, nil
	}
	value, e := parse(asset("weighted_channel"))
	if e != nil {
		return "", e
	}
	weights := doc(at(value, "weights"))
	total := 0.0
	// Literal resource key order is irrelevant to the weighted distribution.
	names := make([]string, 0, len(weights))
	for name, weight := range weights {
		total += num(weight, 0)
		names = append(names, name)
	}
	sort.Strings(names)
	if total <= 0 {
		return "", fault("Config")
	}
	draw := float64(randomIndex(1<<24)) / float64(1<<24) * total
	for _, name := range names {
		weight := num(weights[name], 0)
		if draw < weight {
			channelCache.weighted = name
			return name, nil
		}
		draw -= weight
	}
	return "", fault("Config")
}
func (a *App) identity(module string) (any, string, error) {
	if module == "r_porn" {
		source, e := weightedSource()
		return "@r_porn", source, e
	}
	if module == "reddit2telegram" {
		return "@reddit2telegram", "", nil
	}
	record, e := a.DB.one("channels", D{"submodule": lower(module)}, nil)
	if e != nil {
		return nil, "", e
	}
	if record != nil {
		return at(record, "channel"), field(record, "subreddit"), nil
	}
	local, e := parse(asset("local_channels"))
	if e != nil {
		return nil, "", e
	}
	value, ok := at(local, module).(D)
	if !ok {
		return nil, "", fault("Config")
	}
	return at(value, "t_channel"), field(value, "subreddit"), nil
}
func (a *App) updatePromotionOrder() error {
	modules, e := a.publicModules()
	if e != nil {
		return e
	}
	order := D{}
	for _, module := range modules {
		if module == "reddit2telegram" {
			continue
		}
		destination, _, e := a.identity(module)
		if e != nil {
			return e
		}
		channel, ok := destination.(string)
		if !ok {
			return fault("Config")
		}
		record, e := a.DB.one("view_with_first_dates", D{"_id": lower(channel)}, nil)
		if e != nil {
			return e
		}
		if record != nil && at(record, "first_date") != nil {
			order[module] = at(record, "first_date")
		}
	}
	_, e = a.DB.update("settings", D{"setting": "r2t_promotion_queue"}, D{"$setOnInsert": D{"already_promoted": A{}, "counter": 0}, "$set": D{"promotion_order": order}}, false, true)
	return e
}
func (a *App) promotionTarget() (string, error) {
	channelCache.promotionMu.Lock()
	defer channelCache.promotionMu.Unlock()
	if channelCache.promotion != "" {
		return channelCache.promotion, nil
	}
	modules, e := a.publicModules()
	if e != nil {
		return "", e
	}
	all := []string{}
	active := map[string]bool{}
	for _, module := range modules {
		if module != "reddit2telegram" {
			all = append(all, module)
			active[module] = true
		}
	}
	if len(all) == 0 {
		return "", fault("Config")
	}
	if parts(now(), false).Weekday() == 0 {
		channelCache.promotion = all[randomIndex(len(all))]
		return channelCache.promotion, nil
	}
	record, e := a.DB.one("settings", D{"setting": "r2t_promotion_queue"}, nil)
	if e != nil {
		return "", e
	}
	if record == nil {
		if e = a.updatePromotionOrder(); e != nil {
			return "", e
		}
		record, e = a.DB.one("settings", D{"setting": "r2t_promotion_queue"}, nil)
		if e != nil {
			return "", e
		}
	}
	promoted, ok := at(record, "already_promoted").([]any)
	if !ok {
		return "", fault("Config")
	}
	order, ok := at(record, "promotion_order").(D)
	if !ok {
		return "", fault("Config")
	}
	done := map[string]bool{}
	for _, value := range promoted {
		done[str(value)] = true
	}
	type ordered struct {
		name string
		date float64
	}
	values := []ordered{}
	for name, value := range order {
		stamp, _ := timestamp(value)
		values = append(values, ordered{name, stamp})
	}
	sort.SliceStable(values, func(i, j int) bool {
		if values[i].date == values[j].date {
			return values[i].name < values[j].name
		}
		return values[i].date > values[j].date
	})
	for _, value := range values {
		if active[value.name] && !done[value.name] {
			channelCache.promotion = value.name
			return value.name, nil
		}
	}
	_, e = a.DB.update("settings", D{"setting": "r2t_promotion_queue"}, D{"$inc": D{"counter": 1}, "$set": D{"already_promoted": A{}}}, false, false)
	if e != nil {
		return "", e
	}
	return "", fault("Config")
}
func (a *App) resolve(module string) (*Channel, error) {
	if module == "r_porn" {
		source, e := weightedSource()
		if e != nil {
			return nil, e
		}
		value, e := parse(asset("weighted_channel"))
		if e != nil {
			return nil, e
		}
		options := D{"check_dups": true, "min_upvotes_limit": at(at(value, "limits"), source)}
		for _, kind := range []string{"text", "other", "album", "gif", "img", "video", "gallery"} {
			prefix := "{title}"
			if kind == "text" {
				prefix = "{title}\n\n{self_text}"
			} else if kind == "other" || kind == "album" {
				prefix = "{title}\n{link}"
			}
			options[kind] = prefix + "\n\n{upvotes} upvotes\n/r/{subreddit_name} → #{subreddit_name}\n{short_link}\n{channel}"
		}
		return &Channel{Destination: "@r_porn", Subreddit: source, Options: options, Limit: 100, RequiresSubmission: true}, nil
	}
	if module == "reddit2telegram" {
		target, e := a.promotionTarget()
		if e != nil {
			return nil, e
		}
		_, source, e := a.identity(target)
		if e != nil {
			return nil, e
		}
		return &Channel{Destination: "@reddit2telegram", Subreddit: source, Ranking: "top", Options: D{}, Limit: 1000, RequiresSubmission: true}, nil
	}
	if strings.HasPrefix(module, "tech_") {
		var destination any
		requires := true
		switch module {
		case "tech_receiver":
			destination = "@r_channels"
		case "tech_weekly_radar":
			destination = "@reddit2telegram"
		case "tech_cleaner":
			destination = at(at(a.Config.Values, "telegram"), "dev_chat")
		case "tech_anniversary", "tech_store_stat":
			destination = at(at(a.Config.Values, "telegram"), "dev_chat")
			requires = false
		default:
			return nil, fault("Config")
		}
		return &Channel{Destination: destination, Subreddit: "all", Options: D{}, Limit: 100, RequiresSubmission: requires}, nil
	}
	record, e := a.DB.one("channels", D{"submodule": lower(module)}, nil)
	if e != nil {
		return nil, e
	}
	if record == nil {
		local, e := parse(asset("local_channels"))
		if e != nil {
			return nil, e
		}
		value, ok := at(local, module).(D)
		if !ok {
			return nil, fault("Config")
		}
		limit, exists := value["submissions_limit"]
		if !exists {
			limit = 100
		}
		record = D{"channel": at(value, "t_channel"), "subreddit": at(value, "subreddit"), "submissions_ranking": at(value, "submissions_ranking"), "submissions_limit": limit}
	}
	options := D{"min_upvotes_limit": at(record, "min_upvotes_limit")}
	content := at(record, "content")
	for _, kind := range []string{"text", "gif", "video", "img", "album", "gallery", "other"} {
		if content == nil {
			options[kind] = true
		} else if value, exists := doc(content)[kind]; exists {
			options[kind] = value
		} else {
			options[kind] = false
		}
	}
	ranking := field(record, "submissions_ranking")
	if ranking != "" && ranking != "hot" && ranking != "new" && ranking != "top" {
		ranking = "hot"
	}
	limit := math.MaxInt
	if n, e := whole(at(record, "submissions_limit")); e == nil && n >= 0 && n <= int64(math.MaxInt) {
		limit = int(n)
	}
	return &Channel{Destination: at(record, "channel"), Subreddit: field(record, "subreddit"), Ranking: ranking, Options: options, Limit: limit, RequiresSubmission: true}, nil
}
func (a *App) tags(module string) (string, error) {
	record, e := a.DB.one("channels", D{"submodule": lower(module)}, nil)
	if e != nil {
		return "", e
	}
	if tags := field(record, "tags"); tags != "" {
		return tags, nil
	}
	raw, e := os.ReadFile(filepath.Join(a.Config.App, "channels", module, "tags.txt"))
	if e != nil {
		if os.IsNotExist(e) {
			return "", nil
		}
		return "", fault("Io")
	}
	return string(raw), nil
}
func nice(app *App, module string, submission D, sender *Sender, reddit *Reddit, heading, ending, channel string) (Supply, error) {
	var destination any = channel
	if channel == "" {
		var e error
		destination, _, e = app.identity(module)
		if e != nil {
			return Skip, e
		}
	}
	handle, ok := destination.(string)
	if !ok || !numeric(at(submission, "created_utc")) {
		return Skip, fault("Config")
	}
	tags, e := app.tags(module)
	if e != nil {
		return Skip, e
	}
	tags = strings.Join(strings.Fields(tags), " ")
	options := D{"channel_to_promote": handle, "date": timeText(num(at(submission, "created_utc"), 0), "2006 Jan 02", true), "tags": tags, "extra_ending": ending, "announcement_heading": heading}
	for _, kind := range []string{"text", "other", "album", "gif", "img", "video", "gallery"} {
		prefix := "{announcement_heading}{title}"
		if kind == "text" {
			prefix = "{announcement_heading}{title}\n\n{self_text}"
		} else if kind == "other" || kind == "album" {
			prefix = "{announcement_heading}{title}\n{link}"
		}
		options[kind] = prefix + "\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{date}\n{short_link}\nby {channel_to_promote}\n{tags}\n\n{extra_ending}"
	}
	return sender.simple(submission, options, reddit)
}
func promotion(app *App, submission D, sender *Sender, reddit *Reddit) (Supply, error) {
	current := parts(now(), false)
	weekday := (int(current.Weekday()) + 6) % 7
	if weekday == 5 && (current.Hour() == 0 || current.Hour() == 23) && current.Minute() == 1 {
		return Stop, app.updatePromotionOrder()
	}
	if weekday == 5 {
		return Stop, nil
	}
	hash := sha1Text(current.Format("2006 Jan 02"))
	hour := 0
	for i := 0; i < len(hash); i += 2 {
		value, _ := strconv.ParseInt(hash[i:i+2], 16, 32)
		hour = (hour*256 + int(value)) % 24
	}
	if current.Hour() != hour {
		return Stop, nil
	}
	target, e := app.promotionTarget()
	if e != nil {
		return Skip, e
	}
	result, e := nice(app, target, submission, sender, reddit, "", "", "")
	if e != nil {
		return Skip, e
	}
	if result == Sent && weekday < 5 {
		_, e = app.DB.update("settings", D{"setting": "r2t_promotion_queue"}, D{"$push": D{"already_promoted": target}}, false, false)
	}
	return result, e
}
func channelPost(app *App, module string, channel *Channel, submission D, sender *Sender, reddit *Reddit) (Supply, error) {
	if module == "reddit2telegram" {
		return promotion(app, submission, sender, reddit)
	}
	if strings.HasPrefix(module, "tech_") {
		return channelMaintenance(app, module, sender)
	}
	return sender.simple(submission, channel.Options, reddit)
}
func channelMaintenance(app *App, module string, sender *Sender) (Supply, error) {
	switch module {
	case "tech_cleaner":
		return cleaner(app, sender)
	case "tech_receiver":
		return receiver(app, sender)
	case "tech_weekly_radar":
		return weekly(app, sender)
	case "tech_anniversary":
		return anniversaries(app, sender)
	case "tech_store_stat":
		return achievements(app, sender)
	}
	return Skip, fault("UnknownTask")
}
