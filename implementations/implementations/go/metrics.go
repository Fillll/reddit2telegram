package main

import (
	"os"
	"path/filepath"
	"sync"
	"time"
)

func activeRun(root string) D {
	raw, e := os.ReadFile(filepath.Join(root, "implementations/benchmarks/state/active.json"))
	if e != nil {
		return nil
	}
	value, e := parse(raw)
	if e != nil {
		return nil
	}
	run := doc(value)
	stamp := now()
	if stamp < num(at(run, "started_at"), 1e30) || stamp >= num(at(run, "deadline"), 0) {
		return nil
	}
	return run
}
func emit(run D, event string, fields D) {
	stamp := now()
	if run == nil || stamp < num(at(run, "started_at"), 1e30) || stamp >= num(at(run, "deadline"), 0) {
		return
	}
	path := field(run, "events_path")
	if path == "" {
		return
	}
	fields["schema"] = 1
	fields["run_id"] = at(run, "run_id")
	fields["ts"] = stamp
	fields["event"] = event
	f, e := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0600)
	if e != nil {
		return
	}
	defer f.Close()
	line := []byte(dump(fields) + "\n")
	n, e := f.Write(line)
	if e != nil || n != len(line) {
		logInfo("benchmark event write failed")
	}
}

type Metrics struct {
	Run          D
	Task, Module string
	Wait         any
	Started      time.Time
	mu           sync.Mutex
	counters     D
}

func beginMetrics(root, task, module string, created any) *Metrics {
	run := activeRun(root)
	if run == nil {
		return nil
	}
	var wait any
	if created != nil {
		value := now() - num(created, now())
		if value < 0 {
			value = 0
		}
		wait = value
	}
	m := &Metrics{Run: run, Task: task, Module: module, Wait: wait, Started: time.Now(), counters: D{}}
	emit(run, "job_start", D{"task_id": task, "module": module, "queue_wait_seconds": wait})
	return m
}
func (m *Metrics) count(key string, n uint64) {
	if m == nil {
		return
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	m.counters[key] = int64(num(at(m.counters, key), 0)) + int64(n)
}
func (m *Metrics) finish(err error) {
	if m == nil {
		return
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	status := "success"
	var kind any
	if err != nil {
		status = "failed"
		kind = safe(err).Kind
	}
	emit(m.Run, "job_end", D{"task_id": m.Task, "module": m.Module, "status": status, "error_type": kind,
		"duration_seconds": time.Since(m.Started).Seconds(), "queue_wait_seconds": m.Wait, "counters": clone(m.counters)})
}
func (m *Metrics) post(channel, url string, sent bool) {
	if !sent {
		m.count("candidates_rejected", 1)
		return
	}
	m.count("posts_recorded_sent", 1)
	if m == nil {
		return
	}
	emit(m.Run, "post_record", D{"task_id": m.Task, "post_key": digest([]byte(lower(channel) + "\x00" + lower(url)))})
}
func (m *Metrics) delivery(result any) {
	values := arr(result)
	if values == nil {
		values = A{result}
	}
	for _, message := range values {
		if at(message, "message_id") == nil {
			continue
		}
		m.count("telegram_messages", 1)
		kind := "text_or_other"
		for _, k := range []string{"video", "animation", "photo", "document", "audio"} {
			if at(message, k) != nil {
				kind = k
				break
			}
		}
		m.count("telegram_messages_"+kind, 1)
	}
}
