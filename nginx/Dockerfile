FROM nginx:1.30.3-alpine@sha256:0d3b80406a13a767339fbe2f41406d6c7da727ab89cf8fae399e81f780f814d1

RUN apk add --no-cache --upgrade \
    c-ares=1.34.8-r0 \
    libexpat=2.8.2-r0

COPY nginx/nginx.conf /etc/nginx/nginx.conf

USER nginx
