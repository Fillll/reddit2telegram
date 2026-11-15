package main

import (
	"io"
	"net/http"
	"strings"
	"testing"
)

type testRoundTrip func(*http.Request) (*http.Response, error)

func (f testRoundTrip) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

func fixtureHTTP(handler func(*http.Request) string) *Http {
	client := &http.Client{Transport: testRoundTrip(func(r *http.Request) (*http.Response, error) {
		return &http.Response{StatusCode: 200, Header: http.Header{},
			Body: io.NopCloser(strings.NewReader(handler(r))), Request: r}, nil
	})}
	return &Http{clients: map[bool]*http.Client{false: client, true: client}}
}

func normalSubmission() D {
	return D{"id": "normal", "url": "https://reddit.com/r/test/comments/normal",
		"is_self": true, "is_video": false, "media": nil, "title": "Normal post",
		"selftext": "Body", "subreddit": "test", "score": 100, "over_18": false}
}

func TestRemovedSubmissionRejectedBeforeScoreMediaOrSend(t *testing.T) {
	for _, category := range []string{"content_takedown", "copyright_takedown", "moderator", "deleted", "future_category"} {
		for _, kind := range []string{"text", "img", "video", "gif", "gallery", "album", "other"} {
			t.Run(category+"/"+kind, func(t *testing.T) {
				// Any hydration, classification or send would dereference absent resources.
				result, err := (&Sender{}).simple(D{"removed_by_category": category}, D{"min_upvotes_limit": 100, kind: true}, nil)
				if err != nil || result != Reject {
					t.Fatalf("got %v, %v; want Reject", result, err)
				}
			})
		}
	}
}

func TestUnremovedSubmissionSendsWithoutFetchingRemovalField(t *testing.T) {
	for _, metadata := range []string{"missing", "null", "empty"} {
		t.Run(metadata, func(t *testing.T) {
			post := normalSubmission()
			if metadata == "null" {
				post["removed_by_category"] = nil
			} else if metadata == "empty" {
				post["removed_by_category"] = ""
			}
			calls := 0
			h := fixtureHTTP(func(r *http.Request) string {
				calls++
				if r.URL.Host != "api.telegram.org" || !strings.HasSuffix(r.URL.Path, "/sendMessage") {
					t.Fatalf("unexpected request: %s", r.URL.Redacted())
				}
				return `{"ok":true,"result":{"message_id":1}}`
			})
			sender := &Sender{Destination: "@test", Config: &Config{Values: D{"telegram": D{"token": "offline"}}}, HTTP: h}
			result, err := sender.simple(post, D{}, nil)
			if err != nil || result != Sent || calls != 1 {
				t.Fatalf("got %v, %v, %d requests; want Sent and one request", result, err, calls)
			}
		})
	}
}

func TestRemovalDiscoveredDuringHydrationNeverSends(t *testing.T) {
	for _, missing := range []string{"score", "url", "title", "over_18"} {
		t.Run(missing, func(t *testing.T) {
			post := normalSubmission()
			delete(post, missing)
			full := normalSubmission()
			full["removed_by_category"] = "content_takedown"
			calls := 0
			h := fixtureHTTP(func(r *http.Request) string {
				calls++
				if r.URL.Host != "oauth.reddit.com" || r.URL.Path != "/comments/normal" {
					t.Fatalf("unexpected request: %s", r.URL.Redacted())
				}
				return dump(A{D{"data": D{"children": A{D{"data": full}}}}})
			})
			reddit := &Reddit{Config: &Config{Values: D{}}, HTTP: h, token: "offline", expiry: now() + 3600}
			// No Telegram client or database: sending/marking a duplicate would fail.
			minimum := 1
			if missing == "score" {
				minimum = 200
			}
			result, err := (&Sender{}).simple(post, D{"min_upvotes_limit": minimum, "check_dups": true}, reddit)
			if err != nil || result != Reject || calls != 1 {
				t.Fatalf("got %v, %v, %d requests; want Reject and one hydration", result, err, calls)
			}
		})
	}
}
