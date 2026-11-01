# Native Swift implementation

This work in progress ports the existing application to Swift 6.4.2 on Linux.
All scheduling and application policy will execute in Swift. The C target is
limited to library interop for libmongoc/libbson, libcurl, libyaml, OpenSSL and
Linux allocator/signal APIs; no Python worker implements native application work.

The old server-side MongoDB Swift driver is archived. MongoDB documents direct
use of its C driver as a supported way to use MongoDB from server-side Swift:
<https://www.mongodb.com/community/forums/t/updates-on-mongodb-swift-driver/240047>.
Swift's official Linux installation page lists the pinned compiler image:
<https://www.swift.org/install/linux/ubuntu/24_04/>.

Implemented foundations: pooled MongoDB commands preserving BSON IDs and dates,
streaming HTTP downloads/multipart uploads, YAML configuration, credential-safe
errors, schema-1 benchmark events, Reddit OAuth/listings/hydration and rate pacing.
Business-policy, scheduler, media and maintenance/durable-announcement ports
remain in progress. `fullPortComplete=false` blocks every application role before
configuration is loaded or the queue can be accessed.

The release workflow compiles remotely, records compiler/source/library identity,
and packages the binary with its runtime libraries. `--describe` makes no
application requests and needs no application credentials. No compilation or
metadata output is a live performance result. Keep this branch unmerged during
active Python measurements. Live validation is one fresh 24-hour production run
only after source coverage is complete and the exact artifact has been reviewed.
