// SPDX-License-Identifier: Apache-2.0
#include "config.h"
#include "AuthenticationChallenge.h"

#include <cstdio>
#include <wtf/MainThread.h>
#include <wtf/RefCounted.h>

using namespace WebCore;

class ChallengeClient final : public RefCounted<ChallengeClient>, public AuthenticationClient {
public:
    void ref() const final { RefCounted::ref(); }
    void deref() const final { RefCounted::deref(); }
    void receivedCredential(const AuthenticationChallenge&, const Credential&) final { }
    void receivedRequestToContinueWithoutCredential(const AuthenticationChallenge&) final { ++continuations; }
    void receivedCancellation(const AuthenticationChallenge&) final { }
    void receivedRequestToPerformDefaultHandling(const AuthenticationChallenge&) final { }
    void receivedChallengeRejection(const AuthenticationChallenge&) final { }

    unsigned continuations { 0 };
};

int main()
{
    WTF::initializeMainThread();
    ProtectionSpace space("fixture.clarke.test"_s, 443, ProtectionSpace::ServerType::HTTPS,
        "example realm"_s, ProtectionSpace::AuthenticationScheme::HTTPBasic);
    RefPtr client = adoptRef(*new ChallengeClient);
    auto otherClient = adoptRef(*new ChallengeClient);

    AuthenticationChallenge empty;
    AuthenticationChallenge original(space, Credential(), 0, ResourceResponse(), ResourceError(), client.get());
    AuthenticationChallenge copy = original;
    AuthenticationChallenge unrelated(space, Credential(), 0, ResourceResponse(), ResourceError(), otherClient.ptr());
    if (!empty.isNull() || empty.authenticationClient() || original.isNull())
        return 1;
    if (!AuthenticationChallenge::equalForWebKitLegacyChallengeComparison(original, copy)
        || AuthenticationChallenge::equalForWebKitLegacyChallengeComparison(original, unrelated))
        return 2;
    auto* callback = copy.authenticationClient();
    if (!callback || callback != client.get())
        return 3;
    callback->receivedRequestToContinueWithoutCredential(copy);
    if (client->continuations != 1 || otherClient->continuations)
        return 4;

    client = nullptr;
    if (original.authenticationClient() || copy.authenticationClient() || unrelated.authenticationClient() != otherClient.ptr())
        return 5;
    std::puts("XOS_WEBKIT_CHALLENGE_OK bound_callback comparison expiration");
    return 0;
}
