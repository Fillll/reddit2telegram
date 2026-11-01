package main

import (
	"encoding/base64"
	"fmt"
	"math"
	"strconv"
	"strings"
)

type Reddit struct {
	Config       *Config
	HTTP         *Http
	token        string
	expiry, next float64
}

func newReddit(config *Config, metrics *Metrics) *Reddit {
	return &Reddit{Config: config, HTTP: newHTTP(metrics, false)}
}
func (r *Reddit) close() { r.HTTP.close() }
func (r *Reddit) authorize() error {
	if r.token != "" && now() < r.expiry {
		return nil
	}
	config := doc(at(r.Config.Values, "reddit"))
	auth := base64.StdEncoding.EncodeToString([]byte(field(config, "client_id") + ":" + field(config, "client_secret")))
	body := formBody(D{"grant_type": "password", "username": at(config, "username"), "password": at(config, "password")})
	response, e := r.HTTP.request("POST", "https://www.reddit.com/api/v1/access_token", D{
		"User-Agent": at(config, "user_agent"), "Authorization": "Basic " + auth, "Content-Type": "application/x-www-form-urlencoded"}, strings.NewReader(body), "", 0, false, false)
	if e != nil {
		return e
	}
	if !response.ok() {
		return fault("Reddit")
	}
	data, e := response.json()
	if e != nil {
		return e
	}
	token, ok := at(data, "access_token").(string)
	if !ok {
		return fault("Reddit")
	}
	r.token = token
	r.expiry = now() + num(at(data, "expires_in"), 3600) - 10
	return nil
}
func (r *Reddit) feedback(response *Response) {
	values := make([]float64, 3)
	for i, key := range []string{"x-ratelimit-remaining", "x-ratelimit-reset", "x-ratelimit-used"} {
		value, e := strconv.ParseFloat(response.Headers.Get(key), 64)
		if e != nil {
			return
		}
		values[i] = value
	}
	remaining, reset, used := values[0], values[1], values[2]
	if remaining <= 0 {
		r.next = now() + reset
		return
	}
	r.next = now() + math.Min(reset, math.Min(10, math.Max(0, reset-(600-600/(remaining+used)*used))))
}
func (r *Reddit) get(path string, params D) (any, error) {
	query := doc(clone(params))
	query["raw_json"] = "1"
	endpoint := "https://oauth.reddit.com" + path + "?" + formBody(query)
	for attempt := 0; attempt < 3; attempt++ {
		if attempt > 0 {
			if attempt == 1 {
				pause(0, 2)
			} else {
				pause(2, 4)
			}
		}
		if delay := r.next - now(); delay > 0 {
			pause(delay, delay)
		}
		if e := r.authorize(); e != nil {
			return nil, e
		}
		response, e := r.HTTP.request("GET", endpoint, D{"User-Agent": at(at(r.Config.Values, "reddit"), "user_agent"), "Authorization": "Bearer " + r.token}, nil, "", 0, false, false)
		if e != nil {
			if attempt == 2 {
				return nil, e
			}
			continue
		}
		r.feedback(response)
		code := response.Status
		if code == 401 {
			r.token = ""
			r.expiry = 0
			if attempt < 2 {
				continue
			}
		}
		if (code == 408 || code == 500 || code == 502 || code == 503 || code == 504 || code == 520 || code == 522) && attempt < 2 {
			continue
		}
		if code >= 400 {
			return nil, fault("Reddit")
		}
		return response.json()
	}
	return nil, fault("Reddit")
}
func (r *Reddit) listing(subreddit, ranking string, limit int, after string) (D, error) {
	pageSize := min(limit, 25)
	params := D{"limit": strconv.Itoa(pageSize)}
	if after != "" {
		params["after"] = after
	}
	if ranking == "top" {
		params["t"] = "all"
	}
	response, e := r.get(fmt.Sprintf("/r/%s/%s", subreddit, ranking), params)
	return doc(response), e
}
func (r *Reddit) hydrate(submission D) (D, error) {
	id := field(submission, "id")
	if id == "" {
		return nil, fault("Reddit")
	}
	response, e := r.get("/comments/"+id, D{"limit": "2048", "sort": "confidence"})
	if e != nil {
		return nil, e
	}
	listings := arr(response)
	if len(listings) == 0 {
		return nil, fault("Reddit")
	}
	children := arr(at(at(listings[0], "data"), "children"))
	if len(children) == 0 {
		return nil, fault("Reddit")
	}
	data, ok := at(children[0], "data").(D)
	if !ok {
		return nil, fault("Reddit")
	}
	return data, nil
}
