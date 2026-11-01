package main

import (
	"context"
	"errors"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

type Database struct {
	Client *mongo.Client
	Name   string
}

func newDatabase(config *Config) (*Database, error) {
	values := doc(at(config.Values, "db"))
	uri := field(values, "host")
	if !strings.Contains(uri, "://") {
		uri = "mongodb://" + uri
	}
	client, e := mongo.Connect(options.Client().ApplyURI(uri).SetBSONOptions(&options.BSONOptions{DefaultDocumentM: true}))
	if e != nil || field(values, "name") == "" {
		return nil, fault("Database")
	}
	return &Database{Client: client, Name: field(values, "name")}, nil
}
func (db *Database) close() {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	_ = db.Client.Disconnect(ctx)
}
func databaseError(err error) error {
	if err == nil {
		return nil
	}
	var command mongo.CommandError
	if errors.As(err, &command) {
		return Fault{Kind: "Database", Code: int(command.Code)}
	}
	return fault("Database")
}
func (db *Database) command(command string, value any, fields D) (D, error) {
	// MongoDB requires the command name first; bson.D preserves that order.
	request := bson.D{{Key: command, Value: value}}
	for k, v := range fields {
		request = append(request, bson.E{Key: k, Value: v})
	}
	var raw bson.M
	if e := db.Client.Database(db.Name).RunCommand(context.Background(), request).Decode(&raw); e != nil {
		return nil, databaseError(e)
	}
	result := doc(normalize(raw))
	if values := arr(at(result, "writeErrors")); len(values) > 0 {
		return nil, Fault{Kind: "Database", Code: int(num(at(values[0], "code"), -1))}
	}
	if concern := at(result, "writeConcernError"); concern != nil {
		return nil, Fault{Kind: "Database", Code: int(num(at(concern, "code"), -1))}
	}
	return result, nil
}
func (db *Database) find(collection string, filter, sort D, limit int64, projection D) (A, error) {
	if filter == nil {
		filter = D{}
	}
	fields := D{"filter": filter, "batchSize": int32(1000)}
	if len(sort) > 0 {
		fields["sort"] = sort
	}
	if limit > 0 {
		fields["limit"] = limit
	}
	if len(projection) > 0 {
		fields["projection"] = projection
	}
	result, e := db.command("find", collection, fields)
	if e != nil {
		return nil, e
	}
	cursor := doc(at(result, "cursor"))
	batch, ok := at(cursor, "firstBatch").([]any)
	if !ok {
		return nil, fault("Database")
	}
	out := append(A{}, batch...)
	id, e := whole(at(cursor, "id"))
	if e != nil {
		return nil, fault("Database")
	}
	for id != 0 {
		result, e = db.command("getMore", id, D{"collection": collection, "batchSize": int32(1000)})
		if e != nil {
			return nil, e
		}
		cursor = doc(at(result, "cursor"))
		batch, ok = at(cursor, "nextBatch").([]any)
		if !ok {
			return nil, fault("Database")
		}
		out = append(out, batch...)
		id, e = whole(at(cursor, "id"))
		if e != nil {
			return nil, fault("Database")
		}
	}
	return out, nil
}
func (db *Database) one(collection string, filter, sort D) (D, error) {
	rows, e := db.find(collection, filter, sort, 1, nil)
	if e != nil {
		return nil, e
	}
	if len(rows) == 0 {
		return nil, nil
	}
	return doc(rows[0]), nil
}
func (db *Database) update(collection string, filter, update D, multi, upsert bool) (D, error) {
	return db.command("update", collection, D{"updates": A{D{"q": filter, "u": update, "multi": multi, "upsert": upsert}}, "ordered": true})
}
func (db *Database) claim(collection string, filter, update, sort, projection D, upsert bool) (D, error) {
	fields := D{"query": filter, "update": update, "new": true, "upsert": upsert}
	if len(sort) > 0 {
		fields["sort"] = sort
	}
	if len(projection) > 0 {
		fields["fields"] = projection
	}
	result, e := db.command("findAndModify", collection, fields)
	if e != nil {
		return nil, e
	}
	if at(result, "value") == nil {
		return nil, nil
	}
	return doc(at(result, "value")), nil
}
func (db *Database) insert(collection string, docs A) error {
	if len(docs) == 0 {
		return nil
	}
	_, e := db.command("insert", collection, D{"documents": docs, "ordered": true})
	return e
}
func (db *Database) remove(collection string, filter D, one bool) (int64, error) {
	limit := int32(0)
	if one {
		limit = 1
	}
	result, e := db.command("delete", collection, D{"deletes": A{D{"q": filter, "limit": limit}}, "ordered": true})
	if e != nil {
		return 0, e
	}
	return int64(num(at(result, "n"), 0)), nil
}
func (db *Database) count(collection string, filter D) (int64, error) {
	result, e := db.command("count", collection, D{"query": filter})
	if e != nil {
		return 0, e
	}
	return int64(num(at(result, "n"), 0)), nil
}
