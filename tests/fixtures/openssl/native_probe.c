// SPDX-License-Identifier: Apache-2.0
#include <openssl/evp.h>
#include <openssl/rand.h>
#include <openssl/ssl.h>
#include <openssl/x509v3.h>
#include <stdio.h>
#include <string.h>

static int verify_digest(void)
{
    const unsigned char expected[32] = {
        0xba, 0x78, 0x16, 0xbf, 0x8f, 0x01, 0xcf, 0xea,
        0x41, 0x41, 0x40, 0xde, 0x5d, 0xae, 0x22, 0x23,
        0xb0, 0x03, 0x61, 0xa3, 0x96, 0x17, 0x7a, 0x9c,
        0xb4, 0x10, 0xff, 0x61, 0xf2, 0x00, 0x15, 0xad
    };
    unsigned char digest[EVP_MAX_MD_SIZE];
    size_t length = 0;
    return EVP_Q_digest(NULL, "SHA256", "provider=default", "abc", 3, digest, &length)
        && length == sizeof(expected) && memcmp(digest, expected, length) == 0;
}

static X509 *create_certificate(EVP_PKEY *key)
{
    X509 *certificate = X509_new();
    X509_NAME *subject = certificate ? X509_get_subject_name(certificate) : NULL;
    X509_EXTENSION *name = X509V3_EXT_conf_nid(NULL, NULL, NID_subject_alt_name, "DNS:localhost");
    int ready = subject && name && X509_set_version(certificate, 2)
        && ASN1_INTEGER_set(X509_get_serialNumber(certificate), 1)
        && X509_gmtime_adj(X509_getm_notBefore(certificate), -60)
        && X509_gmtime_adj(X509_getm_notAfter(certificate), 60 * 60)
        && X509_NAME_add_entry_by_txt(subject, "CN", MBSTRING_ASC,
                                     (const unsigned char *)"localhost", -1, -1, 0)
        && X509_set_issuer_name(certificate, subject) && X509_add_ext(certificate, name, -1)
        && X509_set_pubkey(certificate, key) && X509_sign(certificate, key, EVP_sha256()) > 0;
    X509_EXTENSION_free(name);
    if (ready)
        return certificate;
    X509_free(certificate);
    return NULL;
}

static int advance_handshake(SSL *connection)
{
    int result = SSL_do_handshake(connection);
    if (result == 1)
        return 1;
    int error = SSL_get_error(connection, result);
    return error == SSL_ERROR_WANT_READ || error == SSL_ERROR_WANT_WRITE ? 0 : -1;
}

static int exchange(SSL_CTX *client_context, SSL_CTX *server_context, const char *hostname,
                    long expected_verification)
{
    SSL *client = SSL_new(client_context);
    SSL *server = SSL_new(server_context);
    BIO *client_transport = NULL, *server_transport = NULL;
    int verified = 0;
    if (!client || !server || !SSL_set1_host(client, hostname)
        || !BIO_new_bio_pair(&client_transport, 0, &server_transport, 0))
        goto cleanup;
    SSL_set_bio(client, client_transport, client_transport);
    SSL_set_bio(server, server_transport, server_transport);
    client_transport = server_transport = NULL;
    SSL_set_connect_state(client);
    SSL_set_accept_state(server);
    for (int attempt = 0; attempt < 12; ++attempt) {
        int client_status = advance_handshake(client);
        if (client_status < 0) {
            verified = expected_verification != X509_V_OK
                && SSL_get_verify_result(client) == expected_verification;
            break;
        }
        int server_status = advance_handshake(server);
        if (server_status < 0)
            break;
        if (client_status == 1 && server_status == 1) {
            static const char message[] = "XOS OpenSSL";
            char received[sizeof(message)];
            size_t count = 0;
            verified = expected_verification == X509_V_OK && SSL_get_verify_result(client) == X509_V_OK
                && SSL_version(client) == TLS1_3_VERSION && SSL_version(server) == TLS1_3_VERSION
                && SSL_write_ex(client, message, sizeof(message), &count) && count == sizeof(message)
                && SSL_read_ex(server, received, sizeof(received), &count) && count == sizeof(received)
                && memcmp(message, received, sizeof(received)) == 0;
            break;
        }
    }
cleanup:
    BIO_free(client_transport);
    BIO_free(server_transport);
    SSL_free(client);
    SSL_free(server);
    return verified;
}

static int verify_tls(void)
{
    EVP_PKEY *key = EVP_PKEY_Q_keygen(NULL, "provider=default", "EC", "P-256");
    X509 *certificate = key ? create_certificate(key) : NULL;
    SSL_CTX *client = SSL_CTX_new(TLS_client_method());
    SSL_CTX *server = SSL_CTX_new(TLS_server_method());
    if (client)
        SSL_CTX_set_verify(client, SSL_VERIFY_PEER, NULL);
    int ready = certificate && client && server
        && SSL_CTX_set_min_proto_version(client, TLS1_3_VERSION)
        && SSL_CTX_set_min_proto_version(server, TLS1_3_VERSION)
        && X509_STORE_add_cert(SSL_CTX_get_cert_store(client), certificate)
        && SSL_CTX_use_certificate(server, certificate) && SSL_CTX_use_PrivateKey(server, key)
        && exchange(client, server, "localhost", X509_V_OK)
        && exchange(client, server, "other.invalid", X509_V_ERR_HOSTNAME_MISMATCH);
    SSL_CTX_free(client);
    SSL_CTX_free(server);
    X509_free(certificate);
    EVP_PKEY_free(key);
    return ready;
}

int main(void)
{
    if (!verify_digest()) {
        puts("OPENSSL_SHA256_FAILED");
        return 1;
    }

    unsigned char first[32], second[32];
    if (RAND_bytes(first, sizeof(first)) != 1 || RAND_bytes(second, sizeof(second)) != 1
        || memcmp(first, second, sizeof(first)) == 0) {
        puts("OPENSSL_RANDOM_FAILED");
        return 2;
    }

    if (!verify_tls()) {
        puts("OPENSSL_TLS_HANDSHAKE_FAILED");
        return 3;
    }

    puts("XOS_OPENSSL_STATIC_OK sha256 rand tls13 verified_exchange hostname_reject");
    return 0;
}
