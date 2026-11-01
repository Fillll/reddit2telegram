package main

import (
	"bytes"
	"crypto/rand"
	"crypto/sha1"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"math/big"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
	"unicode/utf16"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.yaml.in/yaml/v3"
)

type D map[string]any
type A = []any
type Fault struct {
	Kind string
	Code int
}

func (e Fault) Error() string { return e.Kind }
func fault(kind string) error { return Fault{Kind: kind} }
func safe(err error) Fault {
	if err == nil {
		return Fault{Kind: "None"}
	}
	var f Fault
	if errors.As(err, &f) {
		return f
	}
	return Fault{Kind: "NativeError"}
}

type Supply int

const (
	Sent Supply = iota
	Reject
	Skip
	Stop
)

func doc(v any) D {
	switch x := v.(type) {
	case D:
		return x
	case map[string]any:
		return D(x)
	case bson.M:
		return D(x)
	}
	return D{}
}
func arr(v any) A {
	switch x := v.(type) {
	case []any:
		return x
	case bson.A:
		return []any(x)
	}
	return nil
}
func at(v any, key string) any { return doc(v)[key] }
func str(v any) string {
	if s, ok := v.(string); ok {
		return s
	}
	return ""
}
func field(v any, key string) string { return str(at(v, key)) }
func num(v any, fallback float64) float64 {
	switch x := v.(type) {
	case int:
		return float64(x)
	case int32:
		return float64(x)
	case int64:
		return float64(x)
	case uint64:
		return float64(x)
	case float64:
		return x
	case float32:
		return float64(x)
	case json.Number:
		if n, e := x.Float64(); e == nil {
			return n
		}
	}
	return fallback
}
func whole(v any) (int64, error) {
	switch x := v.(type) {
	case int:
		return int64(x), nil
	case int32:
		return int64(x), nil
	case int64:
		return x, nil
	case json.Number:
		if n, e := x.Int64(); e == nil {
			return n, nil
		}
	case float64:
		if !math.IsNaN(x) && !math.IsInf(x, 0) && math.Trunc(x) == x && x >= -9223372036854775808.0 && x < 9223372036854775808.0 {
			return int64(x), nil
		}
	}
	return 0, fault("Config")
}
func truth(v any) bool {
	switch x := v.(type) {
	case nil:
		return false
	case bool:
		return x
	case string:
		return x != ""
	case D:
		return len(x) > 0
	case []any:
		return len(x) > 0
	}
	return num(v, 1) != 0
}
func normalize(v any) any {
	switch x := v.(type) {
	case map[string]any:
		out := D{}
		for k, v := range x {
			out[k] = normalize(v)
		}
		return out
	case bson.M:
		out := D{}
		for k, v := range x {
			out[k] = normalize(v)
		}
		return out
	case bson.D:
		out := D{}
		for _, e := range x {
			out[e.Key] = normalize(e.Value)
		}
		return out
	case []any:
		out := make(A, len(x))
		for i, v := range x {
			out[i] = normalize(v)
		}
		return out
	case bson.A:
		out := make(A, len(x))
		for i, v := range x {
			out[i] = normalize(v)
		}
		return out
	case json.Number:
		if n, e := x.Int64(); e == nil {
			return n
		}
		if n, e := x.Float64(); e == nil {
			return n
		}
	}
	return v
}
func clone(v any) any {
	switch x := v.(type) {
	case D:
		out := D{}
		for k, v := range x {
			out[k] = clone(v)
		}
		return out
	case []any:
		out := make(A, len(x))
		for i, v := range x {
			out[i] = clone(v)
		}
		return out
	}
	return v
}
func parse(raw []byte) (any, error) {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	var v any
	if decoder.Decode(&v) != nil {
		return nil, fault("Config")
	}
	return normalize(v), nil
}
func dump(v any) string {
	raw, e := json.Marshal(v)
	if e != nil {
		return "null"
	}
	return string(raw)
}
func idString(v any) string {
	if id, ok := v.(bson.ObjectID); ok {
		return id.Hex()
	}
	if s, ok := v.(string); ok {
		return s
	}
	return dump(v)
}
func now() float64                     { return float64(time.Now().UnixNano()) / 1e9 }
func date(stamp float64) bson.DateTime { return bson.DateTime(int64(stamp * 1000)) }
func timestamp(v any) (float64, bool) {
	switch x := v.(type) {
	case bson.DateTime:
		return float64(x) / 1000, true
	case time.Time:
		return float64(x.UnixNano()) / 1e9, true
	}
	return 0, false
}
func parts(stamp float64, utc bool) time.Time {
	t := time.UnixMilli(int64(stamp * 1000))
	if utc {
		return t.UTC()
	}
	return t.In(time.Local)
}
func timeText(stamp float64, layout string, utc bool) string { return parts(stamp, utc).Format(layout) }
func uuid() string {
	var b [16]byte
	if _, e := rand.Read(b[:]); e != nil {
		panic("random source unavailable")
	}
	b[6] = (b[6] & 15) | 64
	b[8] = (b[8] & 63) | 128
	return hex.EncodeToString(b[:])
}
func randomIndex(n int) int {
	if n <= 0 {
		return 0
	}
	v, e := rand.Int(rand.Reader, big.NewInt(int64(n)))
	if e != nil {
		panic("random source unavailable")
	}
	return int(v.Int64())
}
func pause(low, high float64) {
	if high < low {
		high = low
	}
	fraction := float64(randomIndex(1<<24)) / float64(1<<24)
	time.Sleep(time.Duration((low + (high-low)*fraction) * 1e9))
}
func shortSleep(c float64)        { pause(2*c, 4*c) }
func longSleep(c float64)         { pause(8*c, 20*c) }
func digest(raw []byte) string    { v := sha256.Sum256(raw); return hex.EncodeToString(v[:]) }
func sha1Text(raw string) string  { v := sha1.Sum([]byte(raw)); return hex.EncodeToString(v[:]) }
func logInfo(message string)      { fmt.Fprintln(os.Stderr, time.Now().UTC().Format(time.RFC3339), message) }
func utf16Count(value string) int { return len(utf16.Encode([]rune(value))) }
func joinStrings(values A, delimiter string) string {
	out := make([]string, len(values))
	for i, v := range values {
		out[i] = str(v)
	}
	return strings.Join(out, delimiter)
}
func stringsArray(values []string) A {
	out := make(A, len(values))
	for i, v := range values {
		out[i] = v
	}
	return out
}
func human(n int64) string {
	if n > -1000 && n < 1000 {
		return strconv.FormatInt(n, 10)
	}
	v := float64(n)
	suffix := []string{"", "k", "M", "G", "T", "P"}
	i := 0
	for math.Abs(v) >= 1000 && i < 5 {
		i++
		v = math.RoundToEven(v/100) / 10
	}
	return fmt.Sprintf("%.1f%s", v, suffix[i])
}
func render(pattern string, fields D) (string, error) {
	var out strings.Builder
	for i := 0; i < len(pattern); {
		c := pattern[i]
		i++
		if c == '{' || c == '}' {
			if i < len(pattern) && pattern[i] == c {
				out.WriteByte(c)
				i++
				continue
			}
			if c == '}' {
				return "", fault("Template")
			}
			end := strings.IndexByte(pattern[i:], '}')
			if end < 0 {
				return "", fault("Template")
			}
			value, ok := fields[pattern[i:i+end]].(string)
			if !ok {
				return "", fault("Template")
			}
			out.WriteString(value)
			i += end + 1
		} else {
			out.WriteByte(c)
		}
	}
	return out.String(), nil
}

type Config struct {
	Values          D
	Path, App, Root string
}

func loadConfig(filename string) (*Config, error) {
	absolute, e := filepath.Abs(filename)
	if e != nil {
		return nil, fault("Config")
	}
	absolute, e = filepath.EvalSymlinks(absolute)
	if e != nil {
		return nil, fault("Config")
	}
	raw, e := os.ReadFile(absolute)
	if e != nil {
		return nil, fault("Config")
	}
	var values map[string]any
	if yaml.Unmarshal(raw, &values) != nil {
		return nil, fault("Config")
	}
	app := filepath.Dir(filepath.Dir(absolute))
	return &Config{Values: doc(normalize(values)), Path: absolute, App: app, Root: filepath.Dir(app)}, nil
}
func (c *Config) cronPath() string {
	p := field(c.Values, "cron_file")
	if filepath.IsAbs(p) {
		return p
	}
	return filepath.Join(c.App, p)
}
func positive(v any, fallback int) (int, error) {
	if v == nil {
		return fallback, nil
	}
	n, e := whole(v)
	if e != nil || n < 1 || n > math.MaxInt32 {
		return 0, fault("Config")
	}
	return int(n), nil
}
