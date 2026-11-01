package main

import (
	"bytes"
	"compress/gzip"
	"context"
	"crypto/md5"
	"encoding/hex"
	"errors"
	"hash"
	"io"
	"mime/multipart"
	"net"
	"net/http"
	"net/http/httptrace"
	"net/url"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

type Http struct {
	Metrics    *Metrics
	Telegram   bool
	mu         sync.Mutex
	clients    map[bool]*http.Client
	transports []*http.Transport
}
type Response struct {
	Status          int
	Headers         http.Header
	Body            []byte
	TooLarge        bool
	Digest          string
	TransportFailed bool
}

func newHTTP(metrics *Metrics, telegram bool) *Http {
	return &Http{Metrics: metrics, Telegram: telegram, clients: map[bool]*http.Client{}}
}
func (h *Http) close() {
	for _, t := range h.transports {
		t.CloseIdleConnections()
	}
}
func (h *Http) count(key string, n uint64) {
	prefix := "http_"
	if h.Telegram {
		prefix = "telegram_"
	}
	h.Metrics.count(prefix+key, n)
}

type readDeadlineConn struct {
	net.Conn
	read time.Duration
}

func (c *readDeadlineConn) Read(p []byte) (int, error) {
	_ = c.Conn.SetReadDeadline(time.Now().Add(c.read))
	return c.Conn.Read(p)
}
func (c *readDeadlineConn) Write(p []byte) (int, error) {
	_ = c.Conn.SetWriteDeadline(time.Now().Add(c.read))
	return c.Conn.Write(p)
}
func (h *Http) client(head bool) *http.Client {
	h.mu.Lock()
	defer h.mu.Unlock()
	if c := h.clients[head]; c != nil {
		return c
	}
	connect, read := 5*time.Second, 20*time.Second
	if head {
		connect = 3 * time.Second
		read = 8 * time.Second
	}
	if h.Telegram {
		connect = 30 * time.Second
		read = 30 * time.Second
	}
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.DisableCompression = true // Explicit decompression gives body counters the reference's decoded-byte definition.
	transport.ForceAttemptHTTP2 = false // Socket idle deadlines apply to one job's HTTP/1 request.
	transport.DialContext = func(ctx context.Context, network, address string) (net.Conn, error) {
		connection, e := (&net.Dialer{Timeout: connect, KeepAlive: 30 * time.Second}).DialContext(ctx, network, address)
		if e != nil {
			return nil, e
		}
		return &readDeadlineConn{Conn: connection, read: read}, nil
	}
	transport.TLSHandshakeTimeout = connect
	transport.ResponseHeaderTimeout = read
	client := &http.Client{Transport: transport, CheckRedirect: func(request *http.Request, via []*http.Request) error {
		if h.Telegram {
			return http.ErrUseLastResponse
		}
		if len(via) >= 30 {
			return fault("Network")
		}
		return nil
	}}
	h.clients[head] = client
	h.transports = append(h.transports, transport)
	return client
}
func transportError(err error) error {
	var timeout net.Error
	if errors.As(err, &timeout) && timeout.Timeout() {
		return fault("Timeout")
	}
	return fault("Network")
}

type countingReader struct {
	Reader io.Reader
	OnRead func(uint64)
}

func (c countingReader) Read(p []byte) (int, error) {
	n, e := c.Reader.Read(p)
	if n > 0 {
		c.OnRead(uint64(n))
	}
	return n, e
}

// Each request owns its body stream. Count consumed decoded entity bytes, as
// requests.iter_content does in Python; exclude TLS framing and remote URL fetches.
type countedTransport struct {
	h    *Http
	base http.RoundTripper
}

func (t countedTransport) RoundTrip(request *http.Request) (*http.Response, error) {
	t.h.count("request_attempts", 1)
	var writes atomic.Int64
	request = request.WithContext(httptrace.WithClientTrace(request.Context(), &httptrace.ClientTrace{
		WroteHeaders: func() {
			if writes.Add(1) > 1 {
				t.h.count("request_attempts", 1)
			}
		},
	}))
	if request.Body != nil && t.h.Telegram {
		original := request.Body
		request.Body = struct {
			io.Reader
			io.Closer
		}{countingReader{Reader: original, OnRead: func(n uint64) { t.h.count("request_body_bytes", n) }}, original}
		if originalGetBody := request.GetBody; originalGetBody != nil {
			request.GetBody = func() (io.ReadCloser, error) {
				body, err := originalGetBody()
				if err != nil {
					return nil, err
				}
				return struct {
					io.Reader
					io.Closer
				}{countingReader{Reader: body, OnRead: func(n uint64) { t.h.count("request_body_bytes", n) }}, body}, nil
			}
		}
	}
	response, e := t.base.RoundTrip(request)
	if response != nil {
		t.h.count("requests", 1)
		if response.StatusCode >= 400 {
			t.h.count("http_errors", 1)
		}
		if response.StatusCode == 429 {
			t.h.count("rate_limits", 1)
		}
		original := response.Body
		if strings.EqualFold(response.Header.Get("Content-Encoding"), "gzip") && request.Method != "HEAD" {
			decoded, err := gzip.NewReader(original)
			if err != nil {
				_ = original.Close()
				return nil, fault("Network")
			}
			original = &decodedBody{Reader: decoded, decoded: decoded, original: original}
		}
		response.Body = struct {
			io.Reader
			io.Closer
		}{countingReader{Reader: original, OnRead: func(n uint64) { t.h.count("response_body_bytes", n) }}, original}
	}
	return response, e
}

type decodedBody struct {
	io.Reader
	decoded  *gzip.Reader
	original io.Closer
}

func (b *decodedBody) Close() error { _ = b.decoded.Close(); return b.original.Close() }
func (h *Http) request(method, endpoint string, headers D, body io.Reader, output string, limit int64, digestBody, allowInitialFailure bool) (*Response, error) {
	request, e := http.NewRequest(method, endpoint, body)
	if e != nil {
		return nil, fault("Network")
	}
	for k, v := range headers {
		request.Header.Set(k, str(v))
	}
	request.Header.Set("Accept-Encoding", "gzip")
	client := h.client(method == "HEAD")
	// The wrapper is installed once per client, before this job first uses it.
	h.mu.Lock()
	if _, ok := client.Transport.(countedTransport); !ok {
		client.Transport = countedTransport{h: h, base: client.Transport}
	}
	h.mu.Unlock()
	response, e := client.Do(request)
	if e != nil {
		h.count("transport_errors", 1)
		if allowInitialFailure {
			return &Response{Headers: http.Header{}, TransportFailed: true}, nil
		}
		return nil, transportError(e)
	}
	defer response.Body.Close()
	result := &Response{Status: response.StatusCode, Headers: response.Header.Clone()}
	var reader io.Reader = response.Body
	var file *os.File
	var target io.Writer
	var memory bytes.Buffer
	var checksum hash.Hash
	if output != "" {
		file, e = os.OpenFile(output, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0600)
		if e != nil {
			return nil, fault("Io")
		}
		defer file.Close()
		target = file
	} else if digestBody {
		checksum = md5.New()
		target = checksum
	} else {
		target = &memory
	}
	if limit > 0 {
		reader = io.LimitReader(reader, limit+1)
	}
	n, e := io.Copy(target, reader)
	result.TooLarge = limit > 0 && n > limit
	if e != nil && !result.TooLarge {
		h.count("transport_errors", 1)
		return nil, transportError(e)
	}
	if checksum != nil && !result.TooLarge {
		result.Digest = hex.EncodeToString(checksum.Sum(nil))
	}
	result.Body = memory.Bytes()
	return result, nil
}
func (r *Response) ok() bool { return r != nil && r.Status >= 200 && r.Status < 300 }
func (r *Response) json() (any, error) {
	v, e := parse(r.Body)
	if e != nil {
		return nil, fault("Network")
	}
	return v, nil
}
func (h *Http) download(endpoint, path string, limit int64) bool {
	r, e := h.request("GET", endpoint, nil, nil, path, limit, false, false)
	if e != nil || !r.ok() || r.TooLarge {
		_ = os.Remove(path)
		return false
	}
	return true
}
func (h *Http) metadata(endpoint string) (string, error) {
	r, e := h.request("GET", endpoint, nil, nil, "", 1024*1024, false, false)
	if e != nil {
		return "", e
	}
	if !r.ok() || r.TooLarge {
		return "", fault("Media")
	}
	return string(r.Body), nil
}
func formBody(fields D) string {
	values := url.Values{}
	for k, v := range fields {
		values.Set(k, str(v))
	}
	return values.Encode()
}
func (h *Http) api(token, method string, params D, video string) (any, error) {
	endpoint := "https://api.telegram.org/bot" + token + "/" + method
	var r *Response
	var e error
	if video != "" {
		reader, writer := io.Pipe()
		form := multipart.NewWriter(writer)
		contentType := form.FormDataContentType()
		go func() {
			var outcome error
			defer func() { _ = writer.CloseWithError(outcome) }()
			for k, v := range params {
				value := str(v)
				if _, ok := v.(string); !ok {
					value = dump(v)
				}
				if outcome = form.WriteField(k, value); outcome != nil {
					return
				}
			}
			file, err := os.Open(video)
			if err != nil {
				outcome = fault("Io")
				return
			}
			defer file.Close()
			part, err := form.CreateFormFile("video", "video.mp4")
			if err != nil {
				outcome = err
				return
			}
			if _, outcome = io.Copy(part, file); outcome != nil {
				return
			}
			outcome = form.Close()
		}()
		r, e = h.request("POST", endpoint, D{"Content-Type": contentType}, reader, "", 0, false, false)
		_ = reader.Close()
	} else {
		r, e = h.request("POST", endpoint, D{"Content-Type": "application/json"}, strings.NewReader(dump(params)), "", 0, false, false)
	}
	if e != nil {
		return nil, e
	}
	value, e := r.json()
	if e != nil {
		return nil, e
	}
	if !r.ok() || at(value, "ok") != true {
		code := int(num(at(value, "error_code"), float64(r.Status)))
		kind := "Telegram"
		switch code {
		case 400:
			kind = "Rejected"
		case 403:
			kind = "Forbidden"
		case 429:
			kind = "RateLimit"
		}
		return nil, Fault{Kind: kind, Code: code}
	}
	result := at(value, "result")
	h.Metrics.delivery(result)
	return result, nil
}
func lower(value string) string { return strings.ToLower(value) }
