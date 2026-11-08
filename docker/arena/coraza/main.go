// Serveur WAF de l'Arena : Coraza + OWASP Core Rule Set devant le site de test.
//
// Chaque requête reçoit une décision (passe, signale, bloque) avec son score d'anomalie et les règles
// déclenchées. La décision repart vers le frontal dans l'en-tête X-ShadowLab-WAF (JSON en base64) et
// s'ajoute au journal /var/log/arena/coraza.jsonl. Le profil de la requête est choisi par le frontal
// (en-tête X-ShadowLab-Profil) ; les règles de profil sont générées dans /etc/coraza/profils.conf.
package main

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	coreruleset "github.com/corazawaf/coraza-coreruleset/v4"
	"github.com/corazawaf/coraza/v3"
	"github.com/corazawaf/coraza/v3/types"
)

const (
	enteteDecision = "X-ShadowLab-WAF"
	maxRegles      = 25
)

// Règles de l'Arena placées avant le CRS : les échanges internes du système de protection ne sont pas
// inspectés par le WAF (ils transportent des tokens tiers et des cookies de session dont les valeurs
// déclenchent des faux positifs CRS aux niveaux de paranoia élevés, par ex. 942120 sur sl_session).
const exclusions = `
SecRule REQUEST_URI "@beginsWith /lab/collecte" "id:1010,phase:1,pass,nolog,ctl:requestBodyAccess=Off"
SecRule REQUEST_URI "@rx ^/lab/(defi|turnstile|recaptcha|captcha)/verifier" "id:1011,phase:1,pass,nolog,ctl:requestBodyAccess=Off,ctl:ruleRemoveById=942120"
`

type regle struct {
	ID       int    `json:"id"`
	Message  string `json:"message"`
	Severite string `json:"severite"`
}

type decision struct {
	Decision string  `json:"decision"`
	Profil   string  `json:"profil"`
	Score    int     `json:"score"`
	Statut   int     `json:"statut,omitempty"`
	Regles   []regle `json:"regles"`
}

type journal struct {
	sync.Mutex
	f *os.File
}

func (j *journal) ecrire(session, methode, chemin string, d decision) {
	ligne, err := json.Marshal(map[string]any{
		"t": time.Now().UTC().Format(time.RFC3339Nano), "session": session,
		"methode": methode, "chemin": chemin, "decision": d,
	})
	if err != nil || j.f == nil {
		return
	}
	j.Lock()
	defer j.Unlock()
	_, _ = j.f.Write(append(ligne, '\n'))
}

// Points d'anomalie du CRS selon la sévérité (valeurs par défaut de crs-setup).
func points(s types.RuleSeverity) int {
	switch s {
	case types.RuleSeverityCritical:
		return 5
	case types.RuleSeverityError:
		return 4
	case types.RuleSeverityWarning:
		return 3
	case types.RuleSeverityNotice:
		return 2
	}
	return 0
}

func evaluer(tx types.Transaction, profil string, moteurBloque bool) decision {
	d := decision{Decision: "passe", Profil: profil, Regles: []regle{}}
	for _, m := range tx.MatchedRules() {
		meta := m.Rule()
		id := meta.ID()
		// Sans sévérité (901340…) : règles internes du CRS. 949/959/980 : règles de cumul, qui répètent le score.
		p := points(meta.Severity())
		if p == 0 || m.Message() == "" || (id >= 949000 && id < 950000) || (id >= 959000 && id < 960000) || (id >= 980000 && id < 981000) {
			continue
		}
		d.Score += p
		if len(d.Regles) < maxRegles {
			message := m.Message()
			if len(message) > 140 {
				message = message[:140]
			}
			d.Regles = append(d.Regles, regle{ID: id, Message: message, Severite: meta.Severity().String()})
		}
	}
	if moteurBloque {
		d.Decision = "bloque"
	} else if len(d.Regles) > 0 {
		d.Decision = "signale"
	}
	return d
}

func encoder(d decision) string {
	brut, _ := json.Marshal(d)
	return base64.StdEncoding.EncodeToString(brut)
}

type serveur struct {
	waf     coraza.WAF
	journal *journal
	defaut  string
}

func (s *serveur) amont(r *http.Request) *url.URL {
	port := r.Header.Get("X-ShadowLab-Amont")
	if n, err := strconv.Atoi(port); err != nil || n < 1024 || n > 65535 {
		port = s.defaut
	}
	return &url.URL{Scheme: "http", Host: net.JoinHostPort("host.docker.internal", port)}
}

func (s *serveur) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path == "/waf-sante" {
		_, _ = fmt.Fprintln(w, "ok")
		return
	}
	profil := r.Header.Get("X-ShadowLab-Profil")
	session := r.Header.Get("X-ShadowLab-Session")
	tx := s.waf.NewTransaction()
	defer func() {
		tx.ProcessLogging()
		_ = tx.Close()
	}()

	hote, port, _ := net.SplitHostPort(r.RemoteAddr)
	numero, _ := strconv.Atoi(port)
	tx.ProcessConnection(hote, numero, "", 0)
	tx.ProcessURI(r.URL.RequestURI(), r.Method, r.Proto)
	tx.AddRequestHeader("Host", r.Host)
	tx.SetServerName(strings.Split(r.Host, ":")[0])
	for nom, valeurs := range r.Header {
		for _, valeur := range valeurs {
			tx.AddRequestHeader(nom, valeur)
		}
	}

	interruption := tx.ProcessRequestHeaders()
	if interruption == nil && tx.IsRequestBodyAccessible() && r.Body != nil {
		var err error
		interruption, _, err = tx.ReadRequestBodyFrom(r.Body)
		if err != nil {
			http.Error(w, "corps illisible", http.StatusBadRequest)
			return
		}
		if interruption == nil {
			interruption, err = tx.ProcessRequestBody()
			if err != nil {
				http.Error(w, "erreur du WAF", http.StatusInternalServerError)
				return
			}
		}
		corps, err := tx.RequestBodyReader()
		if err == nil {
			r.Body = http.NoBody
			if r.ContentLength != 0 {
				r.Body = readCloser{corps}
			}
		}
	} else if interruption == nil {
		var err error
		interruption, err = tx.ProcessRequestBody()
		if err != nil {
			http.Error(w, "erreur du WAF", http.StatusInternalServerError)
			return
		}
	}

	if interruption != nil {
		statut := interruption.Status
		if statut < 400 {
			statut = http.StatusForbidden
		}
		d := evaluer(tx, profil, true)
		d.Statut = statut
		s.journal.ecrire(session, r.Method, r.URL.Path, d)
		w.Header().Set(enteteDecision, encoder(d))
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.WriteHeader(statut)
		_, _ = fmt.Fprintf(w, "<!doctype html><title>Bloqué</title><body data-arena=\"waf\"><h1>Requête bloquée par le WAF</h1></body>")
		return
	}

	d := evaluer(tx, profil, false)
	s.journal.ecrire(session, r.Method, r.URL.Path, d)
	proxy := httputil.NewSingleHostReverseProxy(s.amont(r))
	proxy.ModifyResponse = func(reponse *http.Response) error {
		reponse.Header.Set(enteteDecision, encoder(d))
		return nil
	}
	proxy.ErrorHandler = func(w http.ResponseWriter, _ *http.Request, err error) {
		log.Printf("amont injoignable : %v", err)
		w.Header().Set(enteteDecision, encoder(d))
		http.Error(w, "site de test injoignable", http.StatusBadGateway)
	}
	proxy.ServeHTTP(w, r)
}

func main() {
	profils, err := os.ReadFile("/etc/coraza/profils.conf")
	if err != nil {
		log.Fatalf("profils introuvables : %v", err)
	}
	waf, err := coraza.NewWAF(coraza.NewWAFConfig().
		WithRootFS(coreruleset.FS).
		WithDirectives("Include @coraza.conf-recommended").
		WithDirectives("SecRuleEngine On").
		WithDirectives("SecResponseBodyAccess Off").
		WithDirectives("SecAuditEngine Off").
		WithDirectives("Include @crs-setup.conf.example").
		WithDirectives(string(profils)).
		WithDirectives(exclusions).
		WithDirectives("Include @owasp_crs/*.conf"))
	if err != nil {
		log.Fatalf("WAF invalide : %v", err)
	}
	fichier, err := os.OpenFile("/var/log/arena/coraza.jsonl", os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
	if err != nil {
		log.Printf("journal indisponible : %v", err)
	}
	defaut := os.Getenv("AMONT_DEFAUT")
	if defaut == "" {
		defaut = "8770"
	}
	log.Println("WAF prêt sur :8782")
	log.Fatal(http.ListenAndServe(":8782", &serveur{waf: waf, journal: &journal{f: fichier}, defaut: defaut}))
}

// readCloser adapte le lecteur du corps conservé par Coraza à ce qu'attend net/http.
type readCloser struct{ lecteur interface{ Read([]byte) (int, error) } }

func (r readCloser) Read(p []byte) (int, error) { return r.lecteur.Read(p) }
func (r readCloser) Close() error               { return nil }
