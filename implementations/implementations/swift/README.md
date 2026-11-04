# Native Swift implementation

This ports the existing scheduled application to Swift 6.4.2 on Linux.
All scheduling and application policy will execute in Swift. The C target is
limited to library interop for libmongoc/libbson, libcurl, libyaml, OpenSSL and
Linux allocator/signal APIs; no Python worker implements native application work.

The old server-side MongoDB Swift driver is archived. MongoDB documents direct
use of its C driver as a supported way to use MongoDB from server-side Swift:
<https://www.mongodb.com/community/forums/t/updates-on-mongodb-swift-driver/240047>.
Swift's official Linux installation page lists the pinned compiler image:
<https://www.swift.org/install/linux/ubuntu/24_04/>.

Source coverage includes the MongoDB task queue, cron scheduler, channel policies,
Reddit OAuth/listings/hydration, Telegram text/media delivery, channel intake,
cleanup, weekly reporting, subscriber snapshots, durable milestone and anniversary
delivery, Sentry/developer reporting and schema-1 benchmark events. See PORTING.md
for the behavior mapping and review limits. No native live trial has run yet.

The compiler uses Swift 5 language mode with optimized release compilation.
Foundation OperationQueue supplies bounded blocking workers, preserving the
reference's sleeping/HTTP-thread architecture. The actual deployed compiler,
source revision, system libraries and literal configuration checksums are
recorded in the packaged artifact. No Python process performs application work.

The release workflow compiles remotely, records compiler/source/library identity,
and packages the binary with its runtime libraries. `--describe` makes no
application requests and needs no application credentials. No compilation or
metadata output is a live performance result. Keep this branch unmerged during
active measurements. Live validation is one fresh 24-hour production run only
after the preceding implementation windows finish and the exact artifact is
reviewed. Refresh the base and release bump before that merge.
