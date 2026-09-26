FROM locustio/locust:2.37.14

# Installed as root into the system site-packages: the container runs as your
# user id so its report is yours, and that user cannot see locust's user site.
USER root
RUN pip install --no-cache-dir "pyjwt[crypto]>=2.8"
USER locust

COPY locustfile.py /mnt/locust/locustfile.py
