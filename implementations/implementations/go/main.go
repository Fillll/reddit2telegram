package main

import (
	"embed"
	"fmt"
	"os"
	"runtime"
	"runtime/debug"
	"slices"
)

//go:embed assets/*.json
var assets embed.FS
var version = "unbuilt"
var sourceCommit = "unbuilt"

const fullPortComplete = false

func asset(name string) []byte {
	raw, e := assets.ReadFile("assets/" + name + ".json")
	if e != nil {
		panic("missing literal asset")
	}
	return raw
}
func metadata() D {
	hashes := D{}
	for _, name := range []string{"local_channels", "weighted_channel", "milestones"} {
		hashes[name] = digest(asset(name))
	}
	var dependencies A
	if info, ok := debug.ReadBuildInfo(); ok {
		for _, dep := range info.Deps {
			dependencies = append(dependencies, D{"module": dep.Path, "version": dep.Version, "sum": dep.Sum})
		}
	}
	return D{"language": "go", "version": version, "source_commit": sourceCommit, "compiler": runtime.Version(),
		"full_port_complete": fullPortComplete, "profile": "optimized default gc compiler; trimpath; CGO_ENABLED=0",
		"configuration_sha256": hashes, "dependencies": dependencies, "gomaxprocs": runtime.GOMAXPROCS(0)}
}
func run() error {
	args := os.Args[1:]
	if slices.Contains(args, "--describe") {
		fmt.Println(dump(metadata()))
		return nil
	}
	if slices.Contains(args, "--version") {
		fmt.Println("r2t-go", version)
		return nil
	}
	if !fullPortComplete {
		return fault("IncompletePort")
	}
	return fault("UnknownTask")
}
func main() {
	if err := run(); err != nil {
		logInfo("r2t-go: " + safe(err).Kind)
		os.Exit(1)
	}
}
