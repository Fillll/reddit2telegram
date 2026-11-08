package main

import (
	"context"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"
)

type Reporter struct {
	events        chan D
	done          chan struct{}
	mu            sync.Mutex
	closing       bool
	dsn, endpoint string
}

func newReporter(config *Config) (*Reporter, error) {
	dsn := field(config.Values, "sentry")
	if dsn == "" {
		return &Reporter{}, nil
	}
	parsed, e := url.Parse(dsn)
	if e != nil || parsed.User == nil || parsed.User.Username() == "" {
		return nil, fault("Config")
	}
	parts := strings.Split(strings.Trim(parsed.Path, "/"), "/")
	if len(parts) == 0 || parts[len(parts)-1] == "" {
		return nil, fault("Config")
	}
	project := parts[len(parts)-1]
	prefix := strings.Join(parts[:len(parts)-1], "/")
	if prefix != "" {
		prefix += "/"
	}
	endpoint := parsed.Scheme + "://" + parsed.Host + "/" + prefix + "api/" + project + "/envelope/"
	r := &Reporter{events: make(chan D, 30), done: make(chan struct{}), dsn: dsn, endpoint: endpoint}
	go func() {
		defer close(r.done)
		client := &http.Client{Timeout: 30 * time.Second}
		defer client.CloseIdleConnections()
		for event := range r.events {
			body := dump(event)
			head := dump(D{"event_id": at(event, "event_id"), "dsn": r.dsn})
			part := dump(D{"type": "event", "length": len(body)})
			ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
			request, e := http.NewRequestWithContext(ctx, "POST", r.endpoint, strings.NewReader(head+"\n"+part+"\n"+body+"\n"))
			if e == nil {
				request.Header.Set("Content-Type", "application/x-sentry-envelope")
				response, err := client.Do(request)
				if response != nil {
					_ = response.Body.Close()
				}
				e = err
			}
			cancel()
			if e != nil {
				logInfo("Sentry reporting failed: Network")
			}
		}
	}()
	return r, nil
}
func (r *Reporter) capture(err error, module string) {
	if r == nil || r.events == nil {
		return
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.closing {
		return
	}
	kind := safe(err).Kind
	event := D{"event_id": uuid(), "timestamp": now(), "platform": "other", "level": "error", "logger": "r2t-go", "release": version,
		"exception": D{"values": A{D{"type": kind, "value": kind}}}, "extra": D{"submodule": module}}
	select {
	case r.events <- event:
	default:
	}
}
func (r *Reporter) close() {
	if r == nil || r.events == nil {
		return
	}
	r.mu.Lock()
	r.closing = true
	close(r.events)
	r.mu.Unlock()
	timer := time.NewTimer(2 * time.Second)
	defer timer.Stop()
	select {
	case <-r.done:
	case <-timer.C:
		// Drop queued envelopes; the goroutine owns any in-flight request and
		// its state remains reachable until it returns.
		for {
			select {
			case _, ok := <-r.events:
				if !ok {
					return
				}
			default:
				return
			}
		}
	}
}

type ErrorContext struct{ Channel, Link string }

func reportDeveloper(app *App, module string, context ErrorContext, err error, metrics *Metrics) error {
	sender := app.sender(at(at(app.Config.Values, "telegram"), "dev_chat"), metrics)
	defer sender.close()
	channel := context.Channel
	if channel == "" {
		channel = sender.channel()
	}
	var filter D
	linkTitle := ""
	if context.Link != "" {
		filter = D{"channel": lower(channel), "url": lower(context.Link)}
		linkTitle = "link: " + context.Link + "\n"
	} else {
		filter = D{"channel": lower(channel), "link": "_NO_", "date": timeText(now(), "2006-01-02", false)}
	}
	record, e := app.DB.claim("errors", filter, D{"$inc": D{"cnt": 1}, "$set": D{"ts": date(now())}}, nil, D{"cnt": 1, "_id": 0}, true)
	if e != nil {
		return e
	}
	count, e := whole(at(record, "cnt"))
	if e != nil {
		return fault("Database")
	}
	body := fmt.Sprintf("<b>r2t error</b>\nsubmodule: %s\nchannel: %s\n%serror_cnt: %d\n\n\n<pre>%s</pre>", module, channel, linkTitle, count, safe(err).Kind)
	_, e = sender.text(body, false, "HTML")
	return e
}
