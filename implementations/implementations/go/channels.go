package main

import (
	"math"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

type Channel struct {
	Destination        any
	Options            D
	Subreddit, Ranking string
	Limit              int
	RequiresSubmission bool
	promotionTarget    string
	recordPromotion    bool
}

var channelCache struct {
	weightedMu sync.Mutex
	weighted   string
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

const promotionQueue = "r2t_promotion_queue"

func (a *App) updatePromotionOrder() error {
	rows, e := a.DB.find("view_with_first_dates", nil, nil, 0, D{"first_date": 1})
	if e != nil || len(rows) == 0 {
		return e
	}
	dates := D{}
	for _, row := range rows {
		dates[field(row, "_id")] = at(row, "first_date")
	}
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
		if value := dates[lower(str(destination))]; value != nil {
			order[module] = value
		}
	}
	_, e = a.DB.update("settings", D{"setting": promotionQueue}, D{"$setOnInsert": D{"already_promoted": A{}, "counter": 0}, "$set": D{"promotion_order": order}}, false, true)
	return e
}

func (a *App) selectPromotion(weekday time.Weekday) (string, error) {
	modules, e := a.publicModules()
	if e != nil {
		return "", e
	}
	candidates := []string{}
	for _, module := range modules {
		if module != "reddit2telegram" {
			candidates = append(candidates, module)
		}
	}
	if len(candidates) == 0 {
		return "", fault("Config")
	}
	if weekday == time.Sunday {
		return candidates[randomIndex(len(candidates))], nil
	}
	filter := D{"setting": promotionQueue}
	record, e := a.DB.one("settings", filter, nil)
	if e != nil {
		return "", e
	}
	if record == nil {
		if e = a.updatePromotionOrder(); e != nil {
			return "", e
		}
		record, e = a.DB.one("settings", filter, nil)
		if e != nil {
			return "", e
		}
	}
	target, reset := nextPromotion(candidates, doc(at(record, "promotion_order")), arr(at(record, "already_promoted")))
	if reset {
		_, e = a.DB.update("settings", filter, D{"$inc": D{"counter": 1}, "$set": D{"already_promoted": A{}}}, false, false)
	}
	return target, e
}

func nextPromotion(candidates []string, dates D, promoted A) (target string, reset bool) {
	// The schedule is the source of eligible channels. A missing date only
	// affects priority, so a missing or stale date view cannot stall rotation.
	sort.Slice(candidates, func(i, j int) bool {
		left, leftKnown := timestamp(dates[candidates[i]])
		right, rightKnown := timestamp(dates[candidates[j]])
		if leftKnown != rightKnown {
			return leftKnown
		}
		if left != right {
			return left > right
		}
		return candidates[i] < candidates[j]
	})
	done := map[string]bool{}
	for _, value := range promoted {
		done[str(value)] = true
	}
	for _, name := range candidates {
		if !done[name] {
			return name, false
		}
	}
	return candidates[0], true
}

func promotionHour(day time.Time) int {
	hash := sha1Text(day.Format("2006 Jan 02"))
	hour := 0
	for i := 0; i < len(hash); i += 2 {
		value, _ := strconv.ParseInt(hash[i:i+2], 16, 32)
		hour = (hour*256 + int(value)) % 24
	}
	return hour
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
		return &Channel{Destination: mainChannel, Ranking: "top", Options: D{}, Limit: 1000, RequiresSubmission: true}, nil
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
	tags = strings.Join(words(tags), " ")
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
func channelPost(app *App, module string, channel *Channel, submission D, sender *Sender, reddit *Reddit) (Supply, error) {
	if module == "reddit2telegram" {
		result, e := nice(app, channel.promotionTarget, submission, sender, reddit, "", "", "")
		if e == nil && result == Sent && channel.recordPromotion {
			_, e = app.DB.update("settings", D{"setting": promotionQueue}, D{"$addToSet": D{"already_promoted": channel.promotionTarget}, "$setOnInsert": D{"counter": 0, "promotion_order": D{}}}, false, true)
		}
		return result, e
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
