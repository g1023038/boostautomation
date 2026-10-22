#!/usr/bin/env bash
set -euo pipefail

cd /opt/jmeter-test

# Optional: trust a corporate TLS-inspecting proxy's root CA if one is mounted
# in at /opt/jmeter-test/certs/corp-ca.crt. Needed only if outbound HTTPS from
# Docker is intercepted the same way it is on the host (see performance/README.md
# for the Windows-side equivalent of this problem). Skipped entirely if absent.
if [ -f ./certs/corp-ca.crt ]; then
    echo "entrypoint: importing ./certs/corp-ca.crt into the JVM truststore"
    keytool -importcert -noprompt -trustcacerts \
        -alias corp-ca \
        -file ./certs/corp-ca.crt \
        -keystore "${JAVA_HOME}/lib/security/cacerts" \
        -storepass changeit
fi

JMX_FILE="${JMX_FILE:-./test.jmx}"
LABEL="${CONTAINER_LABEL:-node}"
RESULTS_DIR="./results"
mkdir -p "$RESULTS_DIR"

DD_ARG=()
if [ -n "${DD_API_KEY:-}" ]; then
    DD_ARG=("-JddApiKey=${DD_API_KEY}")
fi

echo "entrypoint: label=${LABEL} jmx=${JMX_FILE} extra args: $*"

exec jmeter -n \
    -t "$JMX_FILE" \
    -l "${RESULTS_DIR}/${LABEL}.jtl" \
    -j "${RESULTS_DIR}/${LABEL}.jmeter.log" \
    "${DD_ARG[@]}" \
    "$@"
