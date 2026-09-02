/*
 * tracker.js -- the same idea real analytics snippets (Google Analytics,
 * Mixpanel, Segment, ...) use, kept intentionally small:
 *
 *   1. Identify the visitor (localStorage) and the browsing session
 *      (sessionStorage), creating new ids the first time either is seen.
 *   2. On every page load, send a real "page_view" event.
 *   3. On every click on an element marked data-track, send a "click"
 *      (or "conversion", if the element also has data-conversion).
 *   4. When you leave the page, send how long you actually spent on it,
 *      using navigator.sendBeacon so the request survives the page
 *      closing.
 *
 * Every event is POSTed to /api/track on this same site, so there is no
 * cross-origin request involved -- the Flask app in app.py serves both
 * this website and that endpoint.
 */
(function () {
  "use strict";

  var API_URL = "/api/track";

  function randomHex(length) {
    var chars = "0123456789abcdef";
    var out = "";
    for (var i = 0; i < length; i++) out += chars[Math.floor(Math.random() * 16)];
    return out;
  }

  function getVisitor() {
    var id = localStorage.getItem("demo_visitor_id");
    var isNew = false;
    if (!id) {
      id = "V" + randomHex(8);
      localStorage.setItem("demo_visitor_id", id);
      isNew = true;
    }
    return { id: id, isNew: isNew };
  }

  function getSessionId() {
    var id = sessionStorage.getItem("demo_session_id");
    if (!id) {
      id = randomHex(12);
      sessionStorage.setItem("demo_session_id", id);
    }
    return id;
  }

  function getReferrerSource() {
    var params = new URLSearchParams(window.location.search);
    var utm = params.get("utm_source");
    if (utm) return utm.charAt(0).toUpperCase() + utm.slice(1);

    if (!document.referrer) return "Direct";
    try {
      var refHost = new URL(document.referrer).hostname;
      if (refHost === window.location.hostname) return "Internal";
      if (/google|bing|duckduckgo|yahoo/.test(refHost)) return "Organic Search";
      if (/facebook|twitter|x\.com|instagram|linkedin|reddit/.test(refHost)) return "Social Media";
      return "Referral";
    } catch (e) {
      return "Direct";
    }
  }

  var visitor = getVisitor();
  var sessionId = getSessionId();
  var pageCategory = document.body.getAttribute("data-page-category") || "Other";
  var referrerSource = getReferrerSource();
  var loadedAt = Date.now();
  var sentPageExit = false;

  function send(payload, useBeacon) {
    var body = JSON.stringify(Object.assign({
      session_id: sessionId,
      visitor_id: visitor.id,
      visitor_type: visitor.isNew ? "New" : "Returning",
      referrer_source: referrerSource,
      page_name: window.location.pathname,
      page_category: pageCategory
    }, payload));

    if (useBeacon && navigator.sendBeacon) {
      navigator.sendBeacon(API_URL, new Blob([body], { type: "application/json" }));
    } else {
      fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body,
        keepalive: true
      }).catch(function () { /* fire-and-forget: a dropped beat shouldn't break the page */ });
    }
  }

  // 1. Real page view, the moment this script runs.
  send({ event_type: "page_view" });

  // 2. Real clicks -- delegated so it also covers elements added later.
  document.addEventListener("click", function (e) {
    var el = e.target.closest("[data-track]");
    if (!el) return;

    if (el.hasAttribute("data-conversion")) {
      send({
        event_type: "conversion",
        conversion_type: el.getAttribute("data-conversion"),
        conversion_value: parseFloat(el.getAttribute("data-value") || "0")
      });
    } else {
      send({ event_type: "click" });
    }
  });

  // 3. Real dwell time -- fires when you switch tabs, navigate away, or
  // close. This is its own event_type ("page_exit"), separate from
  // "page_view", so a single page visit is never counted twice in the
  // page-view totals -- only used to measure how long you stayed.
  function sendPageExit() {
    if (sentPageExit) return;
    sentPageExit = true;
    var dwell = Math.round((Date.now() - loadedAt) / 1000);
    send({ event_type: "page_exit", time_on_page_seconds: dwell }, true);
  }
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") sendPageExit();
  });
  window.addEventListener("pagehide", sendPageExit);
})();
