package main

import (
	"go.mongodb.org/mongo-driver/v2/bson"
	"sync"
)

func oldestDate() bson.DateTime { return bson.DateTime(-62135596800000) }
func identifiers(event D, key string) (A, error) {
	values, ok := at(event, key).([]any)
	if !ok {
		return nil, fault("Config")
	}
	ids := make(A, len(values))
	for i, value := range values {
		n, e := whole(value)
		if e != nil {
			return nil, e
		}
		ids[i] = n
	}
	return ids, nil
}

type Lease struct {
	DB                        *Database
	Key, Owner, PreviousOwner string
	HasPrevious               bool
}

func newLease(db *Database, key string) *Lease { return &Lease{DB: db, Key: key, Owner: uuid()} }
func (l *Lease) acquire() (bool, error) {
	_, e := l.DB.update("settings", D{"_id": l.Key}, D{"$setOnInsert": D{"setting": l.Key, "expires_at": oldestDate()}}, false, true)
	if e != nil && (safe(e).Kind != "Database" || safe(e).Code != 11000) {
		return false, e
	}
	stamp := now()
	result, e := l.DB.command("findAndModify", "settings", D{"query": D{"_id": l.Key, "expires_at": D{"$lte": date(stamp)}},
		"update": D{"$set": D{"owner": l.Owner, "expires_at": date(stamp + 7200)}}, "new": false})
	if e != nil {
		return false, e
	}
	previous := at(result, "value")
	l.PreviousOwner, l.HasPrevious = at(previous, "owner").(string)
	_, ok := previous.(D)
	return ok, nil
}
func (l *Lease) renew() error {
	stamp := now()
	result, e := l.DB.update("settings", D{"_id": l.Key, "owner": l.Owner, "expires_at": D{"$gt": date(stamp)}}, D{"$set": D{"expires_at": date(stamp + 7200)}}, false, false)
	if e != nil {
		return e
	}
	if num(at(result, "n"), 0) == 0 {
		return fault("Lease")
	}
	return nil
}
func (l *Lease) release() error {
	_, e := l.DB.update("settings", D{"_id": l.Key, "owner": l.Owner}, D{"$set": D{"expires_at": oldestDate()}}, false, false)
	return e
}

type Checkpoint struct {
	DB       *Database
	Selector D
	Path     string
	mu       sync.Mutex
	recorded A
}

func newCheckpoint(db *Database, selector D, path string, recorded A) *Checkpoint {
	return &Checkpoint{DB: db, Selector: doc(clone(selector)), Path: path, recorded: append(A{}, recorded...)}
}
func (c *Checkpoint) ids() A { c.mu.Lock(); defer c.mu.Unlock(); return append(A{}, c.recorded...) }
func (c *Checkpoint) record(ids A) error {
	c.mu.Lock()
	c.recorded = append(c.recorded, ids...)
	all := append(A{}, c.recorded...)
	c.mu.Unlock()
	update := D{"$addToSet": D{"message_ids": D{"$each": ids}}}
	if c.Path != "" {
		update = D{"$set": D{c.Path + ".state": "sent", c.Path + ".message_ids": all, c.Path + ".sent_at": date(now())}}
	}
	result, e := c.DB.update("settings", c.Selector, update, false, false)
	if e != nil {
		return e
	}
	if c.Path != "" && num(at(result, "n"), 0) == 0 {
		return fault("Lease")
	}
	return nil
}
