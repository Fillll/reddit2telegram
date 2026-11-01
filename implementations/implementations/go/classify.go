package main

import (
	"fmt"
	"html"
	"net/url"
	"sort"
	"strings"
)

type Media struct {
	Kind, URL string
	Groups    A
}

func groupsOf(items A) A {
	groups := A{}
	for i := 0; i < len(items); i += 10 {
		groups = append(groups, append(A{}, items[i:min(i+10, len(items))]...))
	}
	return groups
}
func (s *Sender) mimeType(endpoint string) string {
	response, e := s.Media.request("HEAD", endpoint, nil, nil, "", 0, false, false)
	if e != nil {
		return ""
	}
	return response.Headers.Get("Content-Type")
}
func imgurImage(value any) D {
	animated := at(value, "animated") == true
	link := field(value, "link")
	if animated {
		if mp4 := field(value, "mp4"); mp4 != "" {
			link = mp4
		} else if gifv := field(value, "gifv"); gifv != "" {
			link = gifv
		}
	}
	if strings.HasSuffix(link, ".gifv") {
		link = strings.TrimSuffix(link, "v")
	}
	kind := "photo"
	if animated {
		kind = "video"
	}
	return D{"type": kind, "media": link}
}
func (s *Sender) imgur(endpoint string, parsed *url.URL) Media {
	config := doc(at(s.Config.Values, "imgur"))
	if len(config) == 0 {
		if loaded, e := loadConfig(s.Config.App + "/configs/imgur.yml"); e == nil {
			config = loaded.Values
		}
	}
	if len(config) == 0 {
		return Media{Kind: "other", URL: endpoint}
	}
	parts := strings.Split(strings.Trim(parsed.Path, "/"), "/")
	first := parts[0]
	if first == "" || first == "topic" {
		return Media{Kind: "other", URL: endpoint}
	}
	album := first == "a" || first == "gallery"
	index := len(parts) - 1
	if album {
		index = 1
	}
	if index >= len(parts) {
		return Media{Kind: "other", URL: endpoint}
	}
	id := strings.SplitN(parts[index], ".", 2)[0]
	endpoints := []string{"image"}
	if album {
		endpoints = []string{"album", "image"}
	}
	for _, kind := range endpoints {
		if kind == "image" && first == "a" {
			break
		}
		response, e := s.Media.request("GET", "https://api.imgur.com/3/"+kind+"/"+id, D{"Authorization": "Client-ID " + field(config, "client_id")}, nil, "", 0, false, false)
		if e != nil {
			continue
		}
		value, e := response.json()
		if e != nil || at(value, "success") != true {
			continue
		}
		data := at(value, "data")
		if images, ok := at(data, "images").([]any); ok {
			items := A{}
			for _, image := range images {
				items = append(items, imgurImage(image))
			}
			return Media{Kind: "album", URL: endpoint, Groups: groupsOf(items)}
		}
		item := imgurImage(data)
		mediaKind := "img"
		if at(data, "animated") == true {
			mediaKind = "gif"
		}
		return Media{Kind: mediaKind, URL: field(item, "media")}
	}
	return Media{Kind: "other", URL: endpoint}
}
func (s *Sender) classify(submission D) (Media, error) {
	endpoint := field(submission, "url")
	parsed, e := url.Parse(endpoint)
	if e != nil || parsed.Scheme == "" || parsed.Host == "" {
		return Media{}, fault("Media")
	}
	low, host := lower(endpoint), lower(parsed.Hostname())
	if items, ok := at(at(submission, "gallery_data"), "items").([]any); ok {
		numeric, stringsOnly := true, true
		for _, item := range items {
			_, e := whole(at(item, "id"))
			numeric = numeric && e == nil
			_, ok := at(item, "id").(string)
			stringsOnly = stringsOnly && ok
		}
		if !numeric && !stringsOnly {
			return Media{}, fault("Media")
		}
		last := map[string]D{}
		for _, item := range items {
			last[idString(at(item, "id"))] = doc(item)
		}
		ordered := make([]D, 0, len(last))
		for _, item := range last {
			ordered = append(ordered, item)
		}
		sort.Slice(ordered, func(i, j int) bool {
			if numeric {
				a, _ := whole(at(ordered[i], "id"))
				b, _ := whole(at(ordered[j], "id"))
				return a < b
			}
			return field(ordered[i], "id") < field(ordered[j], "id")
		})
		media := A{}
		for _, item := range ordered {
			source := at(at(at(submission, "media_metadata"), field(item, "media_id")), "s")
			link, photo := at(source, "u").(string)
			kind := "photo"
			if !photo {
				link, ok = at(source, "mp4").(string)
				if !ok {
					return Media{}, fault("Media")
				}
				kind = "video"
			}
			decoded := html.UnescapeString(link)
			if u, e := url.Parse(decoded); e == nil && lower(u.Hostname()) == "preview.redd.it" {
				decoded = "https://i.redd.it" + u.EscapedPath()
			} else {
				decoded = strings.ReplaceAll(decoded, "auto=webp", "auto=jpg")
			}
			media = append(media, D{"type": kind, "media": decoded})
		}
		return Media{Kind: "gallery", Groups: groupsOf(media)}, nil
	}
	var video any
	if at(submission, "is_video") == true {
		video = at(at(submission, "media"), "reddit_video")
	}
	if video == nil {
		parents := arr(at(submission, "crosspost_parent_list"))
		if len(parents) > 0 && at(parents[0], "is_video") == true {
			video = at(at(parents[0], "media"), "reddit_video")
		}
	}
	if video != nil {
		kind := "video"
		if at(video, "is_gif") == true {
			kind = "gif"
		}
		return Media{Kind: kind, URL: field(video, "fallback_url")}, nil
	}
	if at(submission, "is_self") == true {
		return Media{Kind: "text"}, nil
	}
	image := strings.HasSuffix(low, ".jpg") || strings.HasSuffix(low, ".jpeg") || strings.HasSuffix(low, ".png")
	if host == "i.redd.it" && image {
		return Media{Kind: "img", URL: endpoint}, nil
	}
	if host == "i.imgur.com" || host == "i.stack.imgur.com" {
		if strings.HasSuffix(low, ".gifv") {
			return Media{Kind: "gif", URL: endpoint[:len(endpoint)-5] + ".mp4"}, nil
		}
		if strings.HasSuffix(low, ".gif") || strings.HasSuffix(low, ".mp4") {
			return Media{Kind: "gif", URL: endpoint}, nil
		}
		if image {
			return Media{Kind: "img", URL: endpoint}, nil
		}
	}
	mime := s.mimeType(endpoint)
	if mime == "image/jpeg" || mime == "image/png" {
		return Media{Kind: "img", URL: endpoint}, nil
	}
	if strings.Contains(mime, "image/gif") {
		if strings.HasSuffix(endpoint, ".gif") {
			mp4 := strings.TrimSuffix(endpoint, ".gif") + ".mp4"
			if s.mimeType(mp4) == "video/mp4" {
				return Media{Kind: "gif", URL: mp4}, nil
			}
		}
		return Media{Kind: "gif", URL: endpoint}, nil
	}
	if strings.HasSuffix(endpoint, ".gifv") {
		mp4 := strings.TrimSuffix(endpoint, ".gifv") + ".mp4"
		if s.mimeType(mp4) == "video/mp4" {
			return Media{Kind: "gif", URL: mp4}, nil
		}
		gif := strings.TrimSuffix(endpoint, "v")
		if s.mimeType(gif) == "image/gif" {
			return Media{Kind: "gif", URL: gif}, nil
		}
	}
	if host == "imgur.com" || host == "www.imgur.com" || host == "m.imgur.com" {
		return s.imgur(endpoint, parsed), nil
	}
	if strings.Contains(host, "gfycat.com") {
		parts := strings.Split(strings.Trim(parsed.Path, "/"), "/")
		index := 0
		if parts[0] == "detail" {
			index = 1
		}
		if index < len(parts) {
			if content, e := s.Media.metadata("https://api.gfycat.com/v1/gfycats/" + parts[index]); e == nil {
				if data, e := parse([]byte(content)); e == nil {
					if link, ok := at(at(data, "gfyItem"), "mp4Url").(string); ok {
						return Media{Kind: "gif", URL: link}, nil
					}
				}
			}
		}
	}
	return Media{Kind: "other", URL: endpoint}, nil
}
func numeric(v any) bool {
	_, e := whole(v)
	if e == nil {
		return true
	}
	_, ok := v.(float64)
	return ok
}
func (s *Sender) simple(initial D, options D, reddit *Reddit) (Supply, error) {
	submission := initial
	var e error
	minimum := at(options, "min_upvotes_limit")
	if numeric(minimum) && at(submission, "score") == nil {
		submission, e = reddit.hydrate(submission)
		if e != nil {
			return Skip, e
		}
	}
	if numeric(minimum) && num(at(submission, "score"), 0) < num(minimum, 0) {
		return Skip, nil
	}
	missing := at(submission, "url") == nil || at(submission, "is_self") == nil ||
		(at(submission, "is_gallery") == true && at(submission, "gallery_data") == nil) ||
		(arr(at(at(submission, "gallery_data"), "items")) != nil && at(submission, "media_metadata") == nil) ||
		(at(submission, "is_video") == true && at(submission, "media") == nil)
	if missing {
		submission, e = reddit.hydrate(submission)
		if e != nil {
			logInfo("HTTP fail prevented at " + s.channel())
			return Skip, nil
		}
	}
	media, e := s.classify(submission)
	if e != nil {
		logInfo("HTTP fail prevented at " + s.channel())
		return Skip, nil
	}
	for _, key := range []string{"title", "selftext", "score", "subreddit", "over_18"} {
		if _, ok := submission[key]; !ok {
			submission, e = reddit.hydrate(submission)
			if e != nil {
				return Skip, e
			}
			break
		}
	}
	_, hasNSFW := options["nsfw_filter_out"]
	if (!hasNSFW || truth(at(options, "nsfw_filter_out"))) && at(submission, "over_18") == true {
		return Reject, nil
	}
	if at(options, "check_dups") == true && media.URL != "" {
		duplicate, e := s.duplicate(media.URL)
		if e != nil {
			return Skip, e
		}
		if duplicate {
			return Reject, nil
		}
	}
	rule, exists := options[media.Kind]
	if !exists {
		rule = true
	}
	if !truth(rule) {
		return Reject, nil
	}
	score := int64(num(at(submission, "score"), 0))
	fields := D{"what": media.Kind, "url": media.URL, "title": field(submission, "title"), "self_text": field(submission, "selftext"),
		"link": field(submission, "url"), "short_link": "https://redd.it/" + field(submission, "id"), "subreddit_name": field(submission, "subreddit"),
		"score": fmt.Sprint(score), "upvotes": human(score), "channel": s.channel()}
	for key, value := range options {
		if v, ok := value.(string); ok {
			fields[key] = v
		} else {
			fields[key] = dump(value)
		}
	}
	fallback := "{title}\n{short_link}\n{channel}"
	switch media.Kind {
	case "text":
		fallback = "{title}\n\n{self_text}\n\n{short_link}\n{channel}"
	case "video", "gallery":
		fallback = "{title}\n\n{short_link}\n{channel}"
	case "album", "other":
		fallback = "{title}\n{link}\n\n{short_link}\n{channel}"
	}
	pattern, ok := rule.(string)
	if !ok {
		pattern = fallback
	}
	if media.Kind == "text" {
		if limit, e := whole(at(options, "max_selftext_len")); e == nil {
			source := []rune(field(submission, "selftext"))
			take := int64(len(source))
			if limit < 0 {
				if limit < -take {
					take = 0
				} else {
					take += limit
				}
			} else {
				take = min(take, limit)
			}
			fields["self_text"] = string(source[:int(take)]) + "..."
		}
		preview := truth(at(options, "disable_web_page_preview"))
		markdown := strings.ReplaceAll(strings.ReplaceAll(pattern, "{short_link}", "[{short_link}]({short_link})"), "{channel}", "[{channel}]({channel})")
		body, e := render(markdown, fields)
		if e != nil {
			return Skip, e
		}
		result, e := s.text(body, preview, "Markdown")
		if e == nil {
			return result, nil
		}
		if safe(e).Kind != "Rejected" {
			return Skip, e
		}
		logInfo("Markdown fail in " + s.channel() + "; sending as plain text.")
		body, e = render(pattern, fields)
		if e != nil {
			return Skip, e
		}
		return s.text(body, preview, "")
	}
	body, e := render(pattern, fields)
	if e != nil {
		return Skip, e
	}
	switch media.Kind {
	case "img":
		return s.image(media.URL, body)
	case "gif":
		return s.gif(media.URL, body)
	case "video":
		return s.video(media.URL, body, field(at(at(submission, "media"), "reddit_video"), "dash_url"))
	case "gallery", "album":
		return s.gallery(media.Groups, body)
	default:
		return s.text(body, false, "")
	}
}
