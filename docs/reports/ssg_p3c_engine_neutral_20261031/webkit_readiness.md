# WebKit provider readiness: requirements, not an integration

Upstream main at `94549a93f9bde9c86c3f2d863e29a2dbd552f7de` contains the
[WebKit port plan](https://github.com/Xiao-John/XylophoneOS/blob/94549a93f9bde9c86c3f2d863e29a2dbd552f7de/docs/plans/webengine_port.md).
[PR #38](https://github.com/Xiao-John/XylophoneOS/pull/38) changed planning and
discipline documents only. The upstream main tree and public repository search
performed for this work did not reveal a WebKit implementation or M0 receipt.
That search is not proof that no private or unadvertised work exists.

| State | Evidence available here |
| --- | --- |
| PLAN_ONLY | Observed: upstream plan and M0–M5 gates. |
| SOURCE_LOCKED | Not evidenced; the plan names a candidate, not a completed M0 source lock. |
| HOST_BUILT | Not evidenced. |
| XOS_CROSS_BUILT | Not evidenced. |
| GUEST_EXECUTED | Not evidenced. |
| WEBENGINE_READY | Not evidenced. |

The synthetic adapter test establishes only substitution of the observation
contract. `WEBKIT_INTEGRATION` remains `NOT_RUN`.

| Requirement for a future provider | Fact or decision needed before claiming support |
| --- | --- |
| DOM node identity | Establish how stable node references are obtained and invalidated within a specific instance, document epoch and frame. No XOS WebKit node API is assumed here. |
| Document lifecycle | Establish navigation, reload, history and document destruction boundaries; advance epoch when old node references are invalid. |
| Frame and iframe boundary | Establish per-frame identity, origin, parent relationship and whether each frame can be observed under the same delegated scope. Unknown or inaccessible frames must remain explicit. |
| Accessible role and name | Identify the actual upstream port's accessibility source, naming algorithm and coverage; distinguish DOM attributes from computed accessibility semantics. |
| Dynamic DOM | Establish revision and observation consistency, mutation ordering, bounded traversal, resets and missed-update behavior. Polling endpoints alone do not imply mutation delivery. |
| Layout and visibility | Establish coordinate spaces, frame transforms, clipping, scroll and fragment completeness. Unknown geometry must not become a zero rectangle or a fabricated diff. |
| Process boundary | The plan targets UIProcess, WebProcess and NetworkProcess in separate tasks. The actual IPC, lifetime, limits and authority delegation remain to be designed against implemented XOS and upstream interfaces. |
| Origin and page permissions | Establish the owner-controlled observation scope and origin/frame policies; a page or provider's self-reported identity cannot grant access. |
| WebProcess exit | Make in-flight work fail or become unknown, invalidate old references, keep unrelated sources observable and require a fresh instance/baseline on trusted restart. |
| Sensitive text and isolation | Establish owner consent, protection propagation, denial across alternative roles and non-republication after revoke. Previously delivered data cannot be retroactively erased. |
| Epoch and revision | Define epoch from real document lifecycle; define source revision from actual engine facts. Keep revision, timestamps and authorization separate. |

The upstream plan reserves M0 for source lock, POSIX gap audit, resource sizing,
port choice and licensing; M1 for JSC/WTF guest execution; M2 for local WebCore
pages; M3 for network services; M4 for the multi-process boundary; and M5 for
HTTPS and security qualification. These are planned gates, not results for this
branch. No guessed WebKit adapter or DOM object is implemented here.
