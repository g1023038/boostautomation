FROM eclipse-temurin:17-jre-jammy

ARG JMETER_VERSION=5.6.3
ARG DD_PLUGIN_VERSION=1.0.0

ENV JMETER_HOME=/opt/apache-jmeter-${JMETER_VERSION}
ENV PATH=${JMETER_HOME}/bin:${PATH}

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Corporate TLS-inspecting proxy (Zscaler) root CA -- without this, every
# HTTPS call made from this network (including the downloads right below,
# and later JMeter's own calls to the real API + Datadog) fails with
# "unable to get local issuer certificate" / PKIX path building errors.
# Trusted for both curl (OS store) and the JVM (its own cacerts) below.
COPY docker/corp-ca.crt /usr/local/share/ca-certificates/corp-ca.crt
RUN update-ca-certificates \
    && keytool -importcert -noprompt -trustcacerts \
        -alias corp-ca \
        -file /usr/local/share/ca-certificates/corp-ca.crt \
        -keystore "${JAVA_HOME}/lib/security/cacerts" \
        -storepass changeit

RUN curl -fsSL "https://dlcdn.apache.org/jmeter/binaries/apache-jmeter-${JMETER_VERSION}.zip" -o /tmp/jmeter.zip \
    && unzip -q /tmp/jmeter.zip -d /opt \
    && rm /tmp/jmeter.zip

# Official Datadog-maintained Backend Listener plugin (Apache 2.0),
# same jar already proven working against this test plan locally.
RUN curl -fsSL \
    "https://repo1.maven.org/maven2/com/datadoghq/jmeter-datadog-backend-listener/${DD_PLUGIN_VERSION}/jmeter-datadog-backend-listener-${DD_PLUGIN_VERSION}-jar-with-dependencies.jar" \
    -o "${JMETER_HOME}/lib/ext/jmeter-datadog-backend-listener-${DD_PLUGIN_VERSION}-jar-with-dependencies.jar"

WORKDIR /opt/jmeter-test

COPY 202609HRv6_BoostRegistrationLoadTest.jmx ./test.jmx
COPY docker/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh \
    && mkdir -p ./results ./data ./certs

VOLUME ["/opt/jmeter-test/results", "/opt/jmeter-test/data", "/opt/jmeter-test/certs"]

ENTRYPOINT ["/opt/jmeter-test/entrypoint.sh"]
