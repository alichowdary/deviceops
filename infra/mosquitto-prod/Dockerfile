FROM eclipse-mosquitto:2.1.2-alpine

COPY --chown=mosquitto:mosquitto mosquitto.conf /mosquitto/config/mosquitto.conf
COPY entrypoint.sh /usr/local/bin/deviceops-mosquitto-entrypoint

RUN chmod 0555 /usr/local/bin/deviceops-mosquitto-entrypoint \
    && chmod 0444 /mosquitto/config/mosquitto.conf

ENTRYPOINT ["/usr/local/bin/deviceops-mosquitto-entrypoint"]
CMD ["/usr/sbin/mosquitto", "-c", "/mosquitto/config/mosquitto.conf"]
