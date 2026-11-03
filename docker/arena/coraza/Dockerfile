FROM golang:1.25-alpine AS construction
WORKDIR /src
COPY go.mod go.sum main.go ./
RUN go mod download && CGO_ENABLED=0 go build -trimpath -ldflags "-s -w" -o /waf .

FROM alpine:3.22
COPY --from=construction /waf /waf
ENTRYPOINT ["/waf"]
