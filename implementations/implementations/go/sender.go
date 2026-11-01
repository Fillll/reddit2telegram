package main

import (
	"context"
	"fmt"
	"html"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"
)

const mediaLimit int64 = 50 * 1024 * 1024

type Ack func(ids A) error
type Sender struct {
	Config      *Config
	DB          *Database
	Destination any
	Metrics     *Metrics
	HTTP, Media *Http
	Videos      chan struct{}
	Ack         Ack
	ownsClients bool
}

func newSender(config *Config, db *Database, destination any, metrics *Metrics, videos chan struct{}) *Sender {
	s := &Sender{Config: config, DB: db, Destination: destination, Metrics: metrics, HTTP: newHTTP(metrics, true), Media: newHTTP(metrics, false), Videos: videos, ownsClients: true}
	shortSleep(1)
	return s
}
func (s *Sender) clone(destination any) *Sender {
	next := *s
	next.Destination = destination
	next.ownsClients = false
	return &next
}
func (s *Sender) close() {
	if s.ownsClients {
		s.HTTP.close()
		s.Media.close()
	}
}
func (s *Sender) channel() string {
	if value, ok := s.Destination.(string); ok {
		return value
	}
	return dump(s.Destination)
}
func (s *Sender) acknowledge(result any) error {
	if s.Ack == nil {
		return nil
	}
	values := arr(result)
	if values == nil {
		values = A{result}
	}
	ids := A{}
	for _, message := range values {
		if id, e := whole(at(message, "message_id")); e == nil {
			ids = append(ids, id)
		}
	}
	return s.Ack(ids)
}
func (s *Sender) api(method string, input D) (any, error) {
	params := doc(clone(input))
	if at(params, "chat_id") == nil && (strings.HasPrefix(method, "send") || method == "getChatMemberCount" || method == "getChatAdministrators") {
		params["chat_id"] = s.Destination
	}
	result, e := s.HTTP.api(field(at(s.Config.Values, "telegram"), "token"), method, params, "")
	if e != nil {
		return nil, e
	}
	if strings.HasPrefix(method, "send") || method == "forwardMessage" {
		if e = s.acknowledge(result); e != nil {
			return nil, e
		}
	}
	return result, nil
}
func splitMessage(body string) (string, string) {
	words := strings.Split(body, " ")
	if utf8.RuneCountInString(words[0]) > 4096 {
		runes := []rune(body)
		return string(runes[:4096]), string(runes[4096:])
	}
	size, take := 0, 0
	for _, word := range words {
		count := utf8.RuneCountInString(word)
		if size+take+count > 4096 {
			break
		}
		size += count
		take++
	}
	return strings.Join(words[:take], " "), strings.Join(words[take:], " ")
}
func splitCaption(body string) (string, string) {
	if utf8.RuneCountInString(body) <= 1024 {
		return body, ""
	}
	words := strings.Split(strings.ReplaceAll(body, "\n", " "), " ")
	caption, tail := "", ""
	switched := false
	for _, word := range words {
		if !switched && utf8.RuneCountInString(caption)+utf8.RuneCountInString(word)+1 < 1020 {
			caption += word + " "
		} else {
			switched = true
			tail += " " + word
		}
	}
	return caption + " ...", "... " + tail
}
func (s *Sender) text(body string, preview bool, mode string) (Supply, error) {
	split := utf8.RuneCountInString(body) >= 4096
	for {
		part, next := body, ""
		if split {
			part, next = splitMessage(body)
		}
		params := D{"text": part, "disable_web_page_preview": preview}
		if mode != "" {
			params["parse_mode"] = mode
		}
		if _, e := s.api("sendMessage", params); e != nil {
			return Skip, e
		}
		if split {
			shortSleep(1)
		}
		if next == "" {
			break
		}
		body = next
	}
	return Sent, nil
}
func (s *Sender) image(endpoint, body string) (Supply, error) {
	if utf8.RuneCountInString(body) > 1024 {
		logInfo("Long pic in " + s.channel() + ".")
		return s.text("<a href=\""+endpoint+"\">&#160;</a>"+body, false, "HTML")
	}
	_, e := s.api("sendPhoto", D{"photo": endpoint, "caption": body})
	if e == nil {
		return Sent, nil
	}
	switch safe(e).Kind {
	case "Rejected", "Telegram", "Network", "Timeout", "Forbidden", "RateLimit":
		return Skip, nil
	}
	return Skip, e
}
func (s *Sender) urlSize(endpoint string) int64 {
	response, e := s.Media.request("HEAD", endpoint, nil, nil, "", 0, false, false)
	if e != nil {
		return 0
	}
	value, _ := strconv.ParseInt(response.Headers.Get("Content-Length"), 10, 64)
	return value
}
func (s *Sender) gif(endpoint, body string) (Supply, error) {
	if s.urlSize(endpoint) > mediaLimit {
		logInfo("Too big.")
		return Reject, nil
	}
	caption, tail := splitCaption(body)
	_, e := s.api("sendDocument", D{"document": endpoint, "caption": caption})
	if e != nil {
		if safe(e).Kind == "Rejected" {
			return Skip, nil
		}
		return Skip, e
	}
	if utf8.RuneCountInString(tail) > 1 {
		shortSleep(1)
		if _, e = s.text(tail, true, ""); e != nil {
			return Skip, e
		}
	}
	return Sent, nil
}
func (s *Sender) gallery(groups A, body string) (Supply, error) {
	if _, e := s.text(body, false, ""); e != nil {
		return Skip, e
	}
	longSleep(1)
	for index, group := range groups {
		if _, e := s.api("sendMediaGroup", D{"media": group}); e != nil {
			logInfo("Gallery sent failed: " + safe(e).Kind)
		} else {
			logInfo("Successful gallery sent.")
		}
		longSleep(float64(index + 2))
	}
	return Sent, nil
}
func (s *Sender) dashAudio(endpoint string) string {
	body, e := s.Media.metadata(endpoint)
	if e != nil {
		return ""
	}
	audio := ""
	for _, match := range regexp.MustCompile(`<BaseURL>([^<]+)</BaseURL>`).FindAllStringSubmatch(body, -1) {
		if strings.Contains(lower(match[1]), "audio") {
			audio = match[1]
		}
	}
	index := strings.Index(endpoint, "DASHPlaylist.mpd")
	if audio == "" || index < 0 {
		return ""
	}
	query := ""
	if i := strings.IndexByte(endpoint, '?'); i >= 0 {
		query = endpoint[i:]
	}
	return endpoint[:index] + audio + query
}
func muxVideo(video, audio, output string) bool {
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()
	command := exec.CommandContext(ctx, "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-threads", "1", "-i", video, "-threads", "1", "-i", audio, "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", output)
	if command.Run() != nil {
		return false
	}
	stat, e := os.Stat(output)
	return e == nil && stat.Size() > 0
}
func (s *Sender) video(endpoint, body, dash string) (Supply, error) {
	s.Videos <- struct{}{}
	defer func() { <-s.Videos }()
	parent := filepath.Join(s.Config.App, "tmp")
	if os.MkdirAll(parent, 0755) != nil {
		return Skip, fault("Io")
	}
	folder, e := os.MkdirTemp(parent, "r2t-")
	if e != nil {
		return Skip, fault("Io")
	}
	defer os.RemoveAll(folder)
	video := filepath.Join(folder, "media.mp4")
	if !s.Media.download(endpoint, video, mediaLimit) {
		return Reject, nil
	}
	audio, muxed := filepath.Join(folder, "media.mp4.aac"), filepath.Join(folder, "media.1.mp4")
	audioURL := ""
	if dash != "" {
		audioURL = s.dashAudio(dash)
	}
	if audioURL == "" {
		parsed, e := url.Parse(endpoint)
		if e != nil {
			return Skip, fault("Media")
		}
		parsed.Path = filepath.ToSlash(filepath.Dir(parsed.Path)) + "/DASH_AUDIO_128.mp4"
		parsed.RawQuery = ""
		parsed.Fragment = ""
		audioURL = parsed.String()
	}
	send := video
	if s.Media.download(audioURL, audio, mediaLimit) && muxVideo(video, audio, muxed) {
		send = muxed
	}
	stat, e := os.Stat(send)
	if e != nil {
		return Skip, fault("Io")
	}
	if stat.Size() <= 0 || stat.Size() > mediaLimit {
		return Reject, nil
	}
	caption, tail := splitCaption(body)
	result, e := s.HTTP.api(field(at(s.Config.Values, "telegram"), "token"), "sendVideo", D{"chat_id": s.Destination, "caption": caption}, send)
	if e != nil {
		return Skip, e
	}
	if e = s.acknowledge(result); e != nil {
		return Skip, e
	}
	if utf8.RuneCountInString(tail) > 1 {
		shortSleep(1)
		if _, e = s.text(tail, true, ""); e != nil {
			return Skip, e
		}
	}
	return Sent, nil
}
func (s *Sender) seen(endpoint string) (bool, error) {
	channel, link := lower(s.channel()), lower(endpoint)
	segments := strings.Split(endpoint, "/")
	id := segments[len(segments)-1]
	filters := []D{{"channel": channel, "url_id": id}, {"channel": channel, "url": link}, {"channel": channel, "url": D{"$regex": regexp.QuoteMeta(id)}}}
	for _, filter := range filters {
		rows, e := s.DB.find("urls", filter, nil, 1, D{"_id": 1})
		if e != nil {
			return false, e
		}
		if len(rows) > 0 {
			s.Metrics.count("previously_seen_candidates", 1)
			return true, nil
		}
	}
	return false, nil
}
func (s *Sender) errorLimit(endpoint string) (bool, error) {
	record, e := s.DB.one("errors", D{"channel": lower(s.channel()), "url": lower(endpoint)}, nil)
	return record != nil && num(at(record, "cnt"), 0) >= 2, e
}
func (s *Sender) mark(endpoint string, sent bool) error {
	segments := strings.Split(endpoint, "/")
	id := segments[len(segments)-1]
	e := s.DB.insert("urls", A{D{"url_id": id, "url": lower(endpoint), "ts": date(now()), "channel": lower(s.channel()), "sent": sent}})
	if e == nil {
		s.Metrics.post(s.channel(), endpoint, sent)
	}
	return e
}
func (s *Sender) duplicate(endpoint string) (bool, error) {
	response, e := s.Media.request("GET", endpoint, nil, nil, "", mediaLimit, true, true)
	if e != nil {
		return false, e
	}
	if !response.ok() || response.TooLarge || response.Digest == "" {
		return false, nil
	}
	channel := lower(s.channel())
	result, e := s.DB.command("findAndModify", "contents", D{"query": D{"channel": channel, "md5_sum": response.Digest},
		"update": D{"$setOnInsert": D{"channel": channel, "md5_sum": response.Digest, "ts": date(now())}}, "upsert": true, "new": false})
	if e != nil {
		return false, e
	}
	duplicate := at(result, "value") != nil
	if duplicate {
		logInfo("Duplicated found!")
		s.Metrics.count("duplicate_media_candidates", 1)
	}
	return duplicate, nil
}
func cleanFiles(config *Config, channel *string) (int64, error) {
	longSleep(1 / (3.141592653589793 * 2.718281828459045))
	path := filepath.Join(config.App, "tmp")
	files, e := os.ReadDir(path)
	if e != nil {
		return 0, fault("Io")
	}
	var total int64
	for _, entry := range files {
		if entry.Name() == "empty.md" {
			continue
		}
		if channel != nil {
			needle := *channel
			if len(needle) > 0 {
				_, size := utf8.DecodeRuneInString(needle)
				needle = needle[size:]
			}
			if !strings.Contains(entry.Name(), needle) {
				continue
			}
		}
		file := filepath.Join(path, entry.Name())
		stat, e := os.Stat(file)
		if e != nil || !stat.Mode().IsRegular() {
			continue
		}
		if os.Remove(file) == nil {
			total += stat.Size()
		}
	}
	return total, nil
}
func htmlEscape(value string) string { return html.EscapeString(value) }
func metadataError(context string, err error) {
	logInfo(fmt.Sprintf("%s: %s", context, safe(err).Kind))
}
