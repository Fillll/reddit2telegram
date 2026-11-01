package main

import (
	"fmt"
	"math"
	"os"
	"os/signal"
	"reflect"
	"runtime"
	"runtime/debug"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"
)

type App struct {
	Config   *Config
	DB       *Database
	Videos   chan struct{}
	Reporter *Reporter
}

func (a *App) sender(destination any, metrics *Metrics) *Sender {
	return newSender(a.Config, a.DB, destination, metrics, a.Videos)
}
func (a *App) jobBody(task D, selector D, metrics *Metrics) (outcome error) {
	defer func() {
		if recover() != nil {
			outcome = fault("NativeError")
		}
	}()
	changed, e := a.DB.update("tasks", selector, D{"$set": D{"status": 2, "updated_at": now()}}, false, false)
	if e != nil {
		return e
	}
	logInfo(fmt.Sprintf("Modified %d docs", int64(num(at(changed, "nModified"), 0))))
	if field(task, "name") != "supply" {
		return fault("UnknownTask")
	}
	args := doc(at(task, "args"))
	module := field(args, "submodule_name")
	config := a.Config
	if values, ok := at(args, "config").(D); ok {
		next := *config
		next.Values = values
		config = &next
	} else if filename, ok := at(args, "config_filename").(string); ok {
		config, e = loadConfig(filename)
		if e != nil {
			return e
		}
	}
	db := a.DB
	if !reflect.DeepEqual(at(config.Values, "db"), at(a.Config.Values, "db")) {
		db, e = newDatabase(config)
		if e != nil {
			return e
		}
		defer db.close()
	}
	job := App{Config: config, DB: db, Videos: a.Videos, Reporter: a.Reporter}
	context := ErrorContext{}
	if e = job.supply(module, metrics, &context); e != nil {
		a.Reporter.capture(e, module)
		if reportDeveloper(&job, module, context, e, metrics) != nil {
			logInfo("developer reporting failed for " + module)
		}
	}
	return e
}
func (a *App) runJob(task D) {
	args := doc(at(task, "args"))
	metrics := beginMetrics(a.Config.Root, idString(at(task, "_id")), field(args, "submodule_name"), at(task, "created_at"))
	selector := D{"_id": at(task, "_id")}
	outcome := a.jobBody(task, selector, metrics)
	if outcome == nil {
		changed, e := a.DB.update("tasks", selector, D{"$set": D{"status": 3, "updated_at": now()}}, false, false)
		outcome = e
		if e == nil {
			logInfo(fmt.Sprintf("Modified %d docs", int64(num(at(changed, "nModified"), 0))))
			logInfo("Task supply successfully executed.")
		}
	}
	if outcome != nil {
		logInfo("Task supply failed: " + safe(outcome).Kind)
		changed, e := a.DB.update("tasks", selector, D{"$set": D{"status": 4, "updated_at": now()}}, false, false)
		if e != nil {
			outcome = e
		} else {
			logInfo(fmt.Sprintf("Modified %d docs", int64(num(at(changed, "nModified"), 0))))
		}
	}
	metrics.finish(outcome)
}
func (a *App) supply(module string, metrics *Metrics, context *ErrorContext) error {
	longSleep(.2)
	channel, e := a.resolve(module)
	if e != nil {
		return e
	}
	context.Channel = idString(channel.Destination)
	if !channel.RequiresSubmission {
		sender := a.sender(channel.Destination, metrics)
		defer sender.close()
		_, e = channelMaintenance(a, module, sender)
		return e
	}
	ranks := []string{"hot", "new", "top"}
	if channel.Ranking != "" {
		ranks = []string{channel.Ranking}
	}
	for _, rank := range ranks {
		reached, e := func() (bool, error) {
			context.Link = ""
			reddit := newReddit(a.Config, metrics)
			defer reddit.close()
			sender := a.sender(channel.Destination, metrics)
			defer sender.close()
			after := ""
			scanned := 0
			reached, stop := false, false
			for scanned < channel.Limit && !stop {
				var page D
				for attempt := 0; attempt < 10; attempt++ {
					page, e = reddit.listing(channel.Subreddit, rank, channel.Limit, after)
					if e == nil {
						break
					}
					if attempt == 9 {
						return reached, e
					}
					metrics.count("reddit_listing_retries", 1)
					longSleep(2.818281828 * math.Pi / 2)
				}
				items, ok := at(at(page, "data"), "children").([]any)
				if !ok {
					return reached, fault("Reddit")
				}
				if len(items) == 0 {
					break
				}
				for _, item := range items {
					if scanned >= channel.Limit {
						break
					}
					scanned++
					submission := doc(at(item, "data"))
					link := "https://redd.it/" + field(submission, "id")
					context.Link = link
					seen, e := sender.seen(link)
					if e != nil {
						return reached, e
					}
					if seen {
						continue
					}
					blocked, e := sender.errorLimit(link)
					if e != nil {
						return reached, e
					}
					if blocked {
						continue
					}
					result, e := channelPost(a, module, channel, submission, sender, reddit)
					if e != nil {
						return reached, e
					}
					reached = true
					switch result {
					case Sent:
						if e = sender.mark(link, true); e != nil {
							return reached, e
						}
						stop = true
					case Reject:
						if e = sender.mark(link, false); e != nil {
							return reached, e
						}
					case Stop:
						stop = true
					}
					if stop {
						break
					}
				}
				after = field(at(page, "data"), "after")
				if after == "" {
					break
				}
			}
			return reached, nil
		}()
		if e != nil {
			return e
		}
		if reached {
			break
		}
	}
	context.Link = ""
	channelName := str(channel.Destination)
	_, e = cleanFiles(a.Config, &channelName)
	return e
}
func consumer(app *App) error {
	size, e := positive(at(at(app.Config.Values, "pool"), "size"), runtime.NumCPU())
	if e != nil {
		return e
	}
	maximum, e := positive(at(at(app.Config.Values, "consumer"), "max_pending"), size)
	if e != nil {
		return e
	}
	batchSize, e := positive(at(at(app.Config.Values, "consumer"), "batch_size"), size*2)
	if e != nil {
		return e
	}
	stopping := make(chan os.Signal, 1)
	signal.Notify(stopping, syscall.SIGTERM, syscall.SIGINT)
	defer signal.Stop(stopping)
	result, e := app.DB.update("tasks", D{"status": D{"$in": A{2, 5}}, "updated_at": D{"$lt": now() - 60}}, D{"$set": D{"status": 1, "updated_at": now()}}, true, false)
	if e != nil {
		return e
	}
	if n := int64(num(at(result, "nModified"), 0)); n > 0 {
		logInfo(fmt.Sprintf("Recovered %d abandoned tasks", n))
	}
	logInfo(fmt.Sprintf("Starting consumer Go with %d workers", size))
	jobs := make(chan D, maximum)
	var pending atomic.Int64
	var workers sync.WaitGroup
	for i := 0; i < size; i++ {
		workers.Add(1)
		go func() {
			defer workers.Done()
			for task := range jobs {
				app.runJob(task)
				pending.Add(-1)
			}
		}()
	}
	defer func() {
		logInfo(fmt.Sprintf("Stopped claiming tasks; draining %d pending jobs", pending.Load()))
		close(jobs)
		workers.Wait()
	}()
	nextMemory := 0.0
	for {
		select {
		case <-stopping:
			return nil
		default:
		}
		if now() >= nextMemory {
			nextMemory = now() + 60
			if raw, e := os.ReadFile("/proc/self/status"); e == nil {
				for _, line := range strings.Split(string(raw), "\n") {
					if strings.HasPrefix(line, "VmRSS:") {
						values := strings.Fields(line)
						if len(values) > 1 {
							if rss, e := strconv.ParseUint(values[1], 10, 64); e == nil && rss >= 256*1024 {
								debug.FreeOSMemory()
							}
						}
						break
					}
				}
			}
		}
		result, e = app.DB.update("tasks", D{"status": 1, "created_at": D{"$lt": now() - 25*60}}, D{"$set": D{"status": 4, "updated_at": now()}}, true, false)
		if e != nil {
			return e
		}
		if n := int64(num(at(result, "nModified"), 0)); n > 0 {
			logInfo(fmt.Sprintf("Failed %d expired new tasks", n))
		}
		available := max(0, maximum-int(pending.Load()))
		take := min(available, batchSize)
		cutoff := now() - 25*60
		batch := []D{}
		for i := 0; i < take; i++ {
			task, e := app.DB.claim("tasks", D{"status": 1, "created_at": D{"$gte": cutoff}}, D{"$set": D{"status": 5, "updated_at": now()}}, D{"created_at": 1}, D{"name": 1, "args": 1, "created_at": 1}, false)
			if e != nil {
				return e
			}
			if task == nil {
				break
			}
			batch = append(batch, task)
		}
		logInfo(fmt.Sprintf("Claimed %d new tasks", len(batch)))
		for _, task := range batch {
			pending.Add(1)
			jobs <- task
		}
		timer := time.NewTimer(5 * time.Second)
		select {
		case <-stopping:
			timer.Stop()
			return nil
		case <-timer.C:
		}
	}
}

type Schedule struct{ Mask, Module string }

func schedules(config *Config) ([]Schedule, error) {
	raw, e := os.ReadFile(config.cronPath())
	if e != nil {
		return nil, fault("Io")
	}
	lines := strings.Split(string(raw), "\n")
	rows := []Schedule{}
	for _, line := range lines[1:] {
		if strings.TrimSpace(line) == "" {
			continue
		}
		parts := strings.Split(line, "\t")
		if len(parts) < 2 {
			return nil, fault("Config")
		}
		rows = append(rows, Schedule{Mask: parts[0], Module: parts[1]})
	}
	return rows, nil
}
func cronNumber(value string) (int, error) {
	for i, day := range []string{"sun", "mon", "tue", "wed", "thu", "fri", "sat"} {
		if lower(value) == day {
			return i, nil
		}
	}
	n, e := strconv.Atoi(value)
	if e != nil || n < 0 || n > math.MaxInt32 {
		return 0, fault("Config")
	}
	return n, nil
}
func cronField(expression string, current, minimum, maximum int) (bool, error) {
	matched := false
	for _, item := range strings.Split(expression, ",") {
		parts := strings.Split(item, "/")
		if len(parts) > 2 {
			return false, fault("Config")
		}
		step := 1
		var e error
		if len(parts) == 2 {
			step, e = cronNumber(parts[1])
			if e != nil {
				return false, e
			}
		}
		if step < 1 {
			return false, fault("Config")
		}
		first, last := minimum, maximum
		if parts[0] != "*" {
			bounds := strings.Split(parts[0], "-")
			if len(bounds) > 2 {
				return false, fault("Config")
			}
			first, e = cronNumber(bounds[0])
			if e != nil {
				return false, e
			}
			last = first
			if len(bounds) == 2 {
				last, e = cronNumber(bounds[1])
				if e != nil {
					return false, e
				}
			} else if len(parts) == 2 {
				last = maximum
			}
		}
		if first < minimum || last > maximum || first > last {
			return false, fault("Config")
		}
		for n := first; n <= last; n += step {
			if n == current || (maximum == 7 && n == 7 && current == 0) {
				matched = true
			}
		}
	}
	return matched, nil
}
func cronMatches(mask string, stamp float64) (bool, error) {
	fields := strings.Fields(mask)
	if len(fields) != 5 {
		return false, fault("Config")
	}
	t := parts(stamp, false)
	values := []int{t.Minute(), t.Hour(), t.Day(), int(t.Month()), int(t.Weekday())}
	mins := []int{0, 0, 1, 1, 0}
	maxs := []int{59, 23, 31, 12, 7}
	matches := make([]bool, 5)
	for i := range fields {
		matched, e := cronField(fields[i], values[i], mins[i], maxs[i])
		if e != nil {
			return false, e
		}
		matches[i] = matched
	}
	dateMatch := matches[2] && matches[4]
	if fields[2] != "*" && fields[4] != "*" {
		dateMatch = matches[2] || matches[4]
	}
	return matches[0] && matches[1] && matches[3] && dateMatch, nil
}
func scheduler(app *App) error {
	stamp := now()
	rows, e := schedules(app.Config)
	if e != nil {
		return e
	}
	modules := []string{}
	for _, row := range rows {
		matched, e := cronMatches(row.Mask, stamp)
		if e != nil {
			return e
		}
		if matched {
			modules = append(modules, row.Module)
		}
	}
	for i := len(modules); i > 1; i-- {
		j := randomIndex(i)
		modules[i-1], modules[j] = modules[j], modules[i-1]
	}
	if len(modules) == 0 {
		return nil
	}
	created := now()
	docs := A{}
	for _, module := range modules {
		docs = append(docs, D{"name": "supply", "args": D{"submodule_name": module, "config_filename": app.Config.Path}, "status": 1, "created_at": created, "updated_at": created})
	}
	if e = app.DB.insert("tasks", docs); e != nil {
		return e
	}
	emit(activeRun(app.Config.Root), "scheduler_submitted", D{"submitted_jobs": len(docs)})
	logInfo(fmt.Sprintf("Inserted %d tasks", len(docs)))
	return nil
}
