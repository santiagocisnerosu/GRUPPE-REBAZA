(async function () {
  "use strict";
  const health = await fetch("/api/health", {cache: "no-store"}).then(r => r.ok && r.json()).catch(() => null);
  if (health?.service !== "receipts-live") return;

  const panel = $("listener-panel"), button = $("new-listener"), form = $("listener-form");
  const description = $("listener-description"), language = $("listener-language"), create = $("create-listener");
  const error = $("listener-error"), steps = [...$("live-steps").children];
  const storageKey = "receipts-live-job";
  let busy = false;

  const anchor = present ? document.querySelector(".stage-top .air-label") : $("meter");
  anchor.after(button);
  button.hidden = false;
  button.onclick = () => {
    panel.showModal();
    if (!busy) description.focus();
  };
  function lock(value) {
    busy = value;
    create.disabled = description.disabled = language.disabled = value;
  }
  function message(text) {
    error.textContent = text;
    error.hidden = !text;
  }
  function progress(job) {
    $("listener-progress").hidden = false;
    const current = steps.findIndex(li => li.dataset.step === job.step);
    steps.forEach((li, i) => {
      if (current >= 0) li.classList.toggle("complete", i < current || job.step === "done");
      if (i === current && job.step !== "done") li.setAttribute("aria-current", "step");
      else li.removeAttribute("aria-current");
    });
    $("live-step").textContent = current >= 0 ? steps[current].textContent : "Failed";
    $("live-meter").textContent = clock(job.elapsed_seconds) + " · $" + job.cost.toFixed(4);
  }
  async function playEdition(id) {
    const entries = await json("listeners.json");
    if (!entries.some(e => e.id === id)) throw Error("The completed edition is missing from the listener list.");
    $("profiles").replaceChildren();
    records.clear();
    for (const entry of entries) makeProfile(entry);
    const url = new URL(location.href);
    url.searchParams.set("listener", id);
    history.replaceState(null, "", url);
    await selectListener(id);
    if (data?.listener !== id || !audio.getAttribute("src")) throw Error("The new audio could not be loaded.");
    panel.close();
    try {
      await audio.play();
    } catch {
      status("Your briefing is ready. Press Play to listen.");
    }
  }
  async function follow(jobId) {
    sessionStorage.setItem(storageKey, jobId);
    for (;;) {
      const response = await fetch("/api/wildcard/" + encodeURIComponent(jobId), {cache: "no-store"});
      if (!response.ok) {
        if (response.status === 404) sessionStorage.removeItem(storageKey);
        throw Error("Could not retrieve this job. Check that the local server is running.");
      }
      const job = await response.json();
      progress(job);
      if (job.step === "failed" || job.step === "done") {
        sessionStorage.removeItem(storageKey);
        if (job.error) throw Error(job.error);
        await playEdition(job.listener_id);
        return;
      }
      await new Promise(resolve => setTimeout(resolve, 750));
    }
  }
  async function run(resume) {
    if (busy) return;
    lock(true);
    message("");
    try {
      let id = resume || sessionStorage.getItem(storageKey);
      if (!id) {
        $("listener-progress").hidden = true;
        const response = await fetch("/api/wildcard", {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({description: description.value.trim(), language: language.value}),
        });
        const result = await response.json();
        if (!response.ok) throw Error(result.error || "Could not start the briefing.");
        id = result.job;
      }
      await follow(id);
    } catch (exc) {
      message(exc.message || "Could not reach the local server.");
    } finally {
      lock(false);
    }
  }
  form.onsubmit = event => {
    event.preventDefault();
    if (!description.value.trim()) { description.focus(); return; }
    run();
  };
  const pending = sessionStorage.getItem(storageKey) || health.active_job;
  if (pending) { panel.showModal(); run(pending); }
})();
