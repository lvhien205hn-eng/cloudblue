/* Supabase GIẢ cho bộ thử trang quản trị (thay file supabase.js thật).
   window.__FAKE_INIT (bộ thử bơm vào trước) = { admin: true|false|null, v41: true|false, v42: true|false, db: {bảng: [dòng]}, settings: {...} }
   v42 = false: cơ sở dữ liệu chưa chạy cloud-pc-v42.sql (không có cột hạn thuê / hàm pc_admin_rent).
   v43 = false: chưa chạy cloud-pc-v43.sql (không có cột user_id / remote của pc_machines, hàm pc_admin_assign). */
(function () {
  const INIT = window.__FAKE_INIT || {};
  const ADMIN_ID = "00000000-0000-4000-8000-000000000001";
  const F = window.__FAKE = { calls: [], v41: INIT.v41 !== false, v42: INIT.v42 !== false, v43: INIT.v43 !== false, db: Object.assign({}, INIT.db || {}), seq: 100, failRpc: {}, delay: 0 };
  const session = INIT.admin === null ? null : { access_token: "x", user: { id: ADMIN_ID, email: "admin@cb.test" } };
  if (session) F.db.profiles = [{ id: ADMIN_ID, username: "chushop", role: INIT.admin === false ? "user" : "admin", locked: false, balance: 0, created_at: new Date().toISOString() }];
  const clone = v => v === undefined ? undefined : JSON.parse(JSON.stringify(v));
  const later = v => new Promise(r => setTimeout(() => r(v), F.delay));
  const isPc = n => /^pc_/.test(n);
  const hex = n => { let s = ""; while (s.length < n) s += Math.floor(Math.random() * 16).toString(16); return s; };
  const noTable = t => ({ data: null, error: { code: "PGRST205", message: "Could not find the table 'public." + t + "' in the schema cache" }, count: null });
  const noFn = f => ({ data: null, error: { code: "PGRST202", message: "Could not find the function public." + f + " without parameters in the schema cache" } });
  const raise = m => ({ data: null, error: { code: "P0001", message: m } });

  function query(table) {
    const st = { table, eq: [], one: false, order: null, limit: null, op: "select", cols: "" };
    const run = () => {
      F.calls.push({ kind: "from", table, op: st.op, eq: st.eq.slice(), cols: st.cols });
      if (isPc(table) && !F.v41) return noTable(table);
      if (isPc(table) && !F.v42 && st.op === "select" && /\b(rent_until|renter|rent_warn_min|rent_remind_min|notify_at)\b/.test(st.cols))        // chưa chạy v42: PostgREST báo thiếu cột
        return { data: null, error: { code: "42703", message: "column " + table + "." + (table === "pc_settings" ? "rent_warn_min" : "rent_until") + " does not exist" }, count: null };
      if (table === "pc_machines" && !F.v43 && st.op === "select" && /\b(user_id|remote)\b/.test(st.cols))
        return { data: null, error: { code: "42703", message: "column pc_machines.user_id does not exist" }, count: null };
      if (st.op !== "select") return { data: null, error: null };
      if (table === "pc_settings" && F.v42) sets();                   // cột v42 có giá trị mặc định (NOT NULL) như cơ sở dữ liệu thật
      let rows = (F.db[table] || []).filter(r => st.eq.every(([c, v]) => String(r[c]) === String(v)));
      if (st.order) { const [c, asc] = st.order; rows = rows.slice().sort((a, b) => (a[c] > b[c] ? 1 : a[c] < b[c] ? -1 : 0) * (asc ? 1 : -1)); }
      if (st.limit != null) rows = rows.slice(0, st.limit);
      return st.one ? { data: clone(rows[0]) || null, error: null } : { data: clone(rows), error: null, count: rows.length };
    };
    const api = {
      select(c) { st.cols = String(c || ""); return p; }, eq(c, v) { st.eq.push([c, v]); return p; }, order(c, o) { st.order = [c, !(o && o.ascending === false)]; return p; },
      limit(n) { st.limit = n; return p; }, maybeSingle() { st.one = true; return p; }, single() { st.one = true; return p; },
      insert() { st.op = "insert"; return p; }, update() { st.op = "update"; return p; }, upsert() { st.op = "upsert"; return p; }, delete() { st.op = "delete"; return p; },
      then(a, b) { return later(run()).then(a, b); }, catch(b) { return later(run()).catch(b); }, finally(f) { return later(run()).finally(f); },
    };
    const p = new Proxy(api, { get(t, k) { if (k in t) return t[k]; if (typeof k === "symbol") return undefined; return () => p; } });
    return p;
  }

  const pcs = () => (F.db.pc_machines = F.db.pc_machines || []);
  const ords = () => (F.db.pc_orders = F.db.pc_orders || []);
  const sets = () => { F.db.pc_settings = F.db.pc_settings || [{ id: 1, enroll_hash: null, enroll_made_at: null, auto_approve: false, agent: {}, poll_s: 30 }];
    const s = F.db.pc_settings[0]; if (F.v42) for (const [k, v] of [["rent_warn_min", 2880], ["rent_remind_min", 240], ["off_alert_min", 15], ["alert_email", true], ["notify_at", null], ["notify_fail_at", null], ["notify_err", null]]) if (!(k in s)) s[k] = v;
    return s; };
  const RPC = {
    pc_admin_new_key() { const k = "cbpc_" + hex(40); const s = sets(); s.enroll_hash = "h" + hex(63); s.enroll_made_at = new Date().toISOString(); return { data: k, error: null }; },
    pc_admin_key_off() { const s = sets(); s.enroll_hash = null; s.enroll_made_at = null; return { data: null, error: null }; },
    pc_admin_settings(a) { const s = sets(), p = a.p_patch || {}; if ("auto_approve" in p) s.auto_approve = !!p.auto_approve; if ("agent" in p) { if (!p.agent || typeof p.agent !== "object" || Array.isArray(p.agent)) return raise("BAD_AGENT"); s.agent = clone(p.agent); } if ("poll_s" in p) s.poll_s = +p.poll_s;
      if (F.v42) {                                                 // v41 bỏ qua các khoá lạ (đúng như hàm SQL cũ)
        for (const [k, max] of [["rent_warn_min", 10080], ["rent_remind_min", 1440], ["off_alert_min", 1440]]) if (k in p) { const n = +p[k]; if (!Number.isInteger(n) || n < 0 || n > max) return raise("BAD_WARN"); s[k] = n; }
        if ("alert_email" in p) s.alert_email = !!p.alert_email;
      }
      return { data: clone(s), error: null }; },
    pc_admin_rent(a) {                                             // như hàm SQL v42: {add_hours} nối vào hạn còn hiệu lực · {until: iso|null} · {renter}
      if (!F.v42) return noFn("pc_admin_rent");
      const m = pcs().find(x => x.id === a.p_id), p = a.p_patch; if (!p || typeof p !== "object" || Array.isArray(p)) return raise("BAD_PATCH"); if (!m) return raise("NO_MACHINE");
      let u = m.rent_until ? new Date(m.rent_until).getTime() : null, touch = false;
      if ("add_hours" in p) { const h = +p.add_hours; if (!/^[0-9]{1,5}(\.[0-9]{1,3})?$/.test(String(p.add_hours)) || !(h > 0) || h > 8784) return raise("BAD_HOURS"); u = Math.max(u || 0, Date.now()) + h * 3600e3; touch = true; }
      else if ("until" in p) { if (p.until === null) u = null; else { u = new Date(p.until).getTime(); if (isNaN(u) || u < Date.now() - 60e3 || u > Date.now() + 2 * 366 * 86400e3) return raise("BAD_UNTIL"); } touch = true; }
      m.rent_until = u === null ? null : new Date(u).toISOString();
      if ("renter" in p) m.renter = String(p.renter || "").trim().slice(0, 80) || null;
      if (touch) { m.rent_set_at = new Date().toISOString(); m.rent_off_at = null; if (u !== null && m.approved && ["ready", "rented"].includes(m.status)) m.status = "rented"; else if (u === null && m.status === "rented") m.status = "ready"; }
      return { data: clone(m), error: null };
    },
    pc_admin_set(a) {
      const m = pcs().find(x => x.id === a.p_id), p = a.p_patch || {}; if (!m) return raise("NO_MACHINE");
      if ("name" in p) { const n = String(p.name || "").trim(); if (!n || n.length > 40) return raise("BAD_NAME"); m.name = n; }
      let st = "status" in p ? p.status : null; if (st && !["new", "ready", "rented", "maint"].includes(st)) return raise("BAD_STATUS");
      const ap = "approved" in p ? !!p.approved : null;
      if (ap === true && !st && m.status === "new") st = "ready"; if (ap === false && !st && m.status === "ready") st = "new";
      if ("code" in p) m.code = String(p.code || "").trim().slice(0, 40) || null; if ("note" in p) m.note = String(p.note || "").trim().slice(0, 500) || null;
      if (ap !== null) m.approved = ap; if (st) m.status = st; return { data: clone(m), error: null };
    },
    pc_admin_order(a) {
      const m = pcs().find(x => x.id === a.p_id); if (!m) return raise("NO_MACHINE");
      if (!["reinstall", "reboot", "shutdown", "update"].includes(a.p_cmd)) return raise("BAD_CMD");
      if (ords().some(o => o.pc_id === m.id && o.cmd === "reinstall" && (o.state === "queued" || o.state === "sent"))) return raise("BUSY");
      let args = {};
      if (a.p_cmd === "reinstall") { const g = a.p_args || {}; if (!/^[a-z0-9]{2,12}$/.test(g.os || "")) return raise("BAD_OS"); if (!["all", "disk", "system"].includes(g.wipe || "all")) return raise("BAD_WIPE"); args = { os: g.os, wipe: g.wipe || "all", ticket: hex(32) }; }
      const o = { id: ++F.seq, pc_id: m.id, cmd: a.p_cmd, args, state: "queued", result: null, created_at: new Date().toISOString(), sent_at: null, done_at: null };
      ords().push(o); return { data: clone(o), error: null };
    },
    pc_admin_order_cancel(a) { const o = ords().find(x => x.id === a.p_order && (x.state === "queued" || x.state === "sent")); if (!o) return raise("NOT_OPEN"); o.state = "cancelled"; o.done_at = new Date().toISOString(); delete o.args.ticket; return { data: clone(o), error: null }; },
    pc_admin_allow_reenroll(a) { const m = pcs().find(x => x.id === a.p_id); if (!m) return raise("NO_MACHINE"); m.reenroll_until = new Date(Date.now() + (a.p_hours || 6) * 3600e3).toISOString(); return { data: clone(m), error: null }; },
    pc_admin_assign(a) {                                           // như hàm SQL v43: {user: tên đăng nhập | email | ""} · {remote: true|false}
      if (!F.v43) return noFn("pc_admin_assign");
      const m = pcs().find(x => x.id === a.p_id), p = a.p_patch; if (!p || typeof p !== "object" || Array.isArray(p)) return raise("BAD_PATCH"); if (!m) return raise("NO_MACHINE");
      let u = m.user_id || null;
      if ("user" in p) {
        const who = String(p.user == null ? "" : p.user).trim().toLowerCase();
        if (!who) u = null;
        else { const f = (F.db.profiles || []).filter(r => String(r.username || "").toLowerCase() === who || (who.includes("@") && String(r.email || "").toLowerCase() === who));
          if (!f.length) return raise("NO_USER"); if (f.length > 1) return raise("MANY_USERS"); u = f[0].id; }
      }
      if ("remote" in p && typeof p.remote !== "boolean") return raise("BAD_PATCH");
      m.user_id = u; if ("remote" in p) m.remote = p.remote; else if (m.remote === undefined) m.remote = true;
      return { data: clone(m), error: null };
    },
    pc_admin_delete(a) { F.db.pc_machines = pcs().filter(x => x.id !== a.p_id); F.db.pc_orders = ords().filter(o => o.pc_id !== a.p_id); return { data: null, error: null }; },
  };
  function rpc(name, args) {
    const run = () => {
      F.calls.push({ kind: "rpc", name, args: clone(args || {}) });
      if (F.failRpc[name]) return raise(F.failRpc[name]);
      const hk = (window.__FAKE_HOOK || {})[name];                    // bộ thử tự trả lời hàm này (phần bán VPS GPU — v43)
      if (typeof hk === "function") { try { const r = hk(clone(args || {}), F); return r && ("data" in r || "error" in r) ? r : { data: r === undefined ? null : r, error: null }; } catch (e) { return raise(String(e && e.message || e)); } }
      if (isPc(name)) { if (!F.v41) return noFn(name); if (INIT.admin === false) return raise("NOT_ADMIN"); if (RPC[name]) return RPC[name](args || {}); }
      return { data: null, error: null };
    };
    const api = { then(a, b) { return later(run()).then(a, b); }, catch(b) { return later(run()).catch(b); }, finally(f) { return later(run()).finally(f); } };
    const p = new Proxy(api, { get(t, k) { if (k in t) return t[k]; if (typeof k === "symbol") return undefined; return () => p; } });
    return p;
  }
  const ok = v => () => Promise.resolve({ data: v, error: null });
  const client = {
    from: query, rpc,
    auth: {
      onAuthStateChange(cb) { setTimeout(() => cb(session ? "SIGNED_IN" : "INITIAL_SESSION", session), 0); return { data: { subscription: { unsubscribe() {} } } }; },
      getSession: ok({ session }), getUser: ok({ user: session && session.user }), signOut: ok({}), updateUser: ok({}), resetPasswordForEmail: ok({}),
      signUp: ok({}), signInWithPassword: ok({ session }), verifyOtp: ok({}),
    },
    storage: { from: () => new Proxy({}, { get: (t, k) => k === "getPublicUrl" ? () => ({ data: { publicUrl: "" } }) : ok(null) }) },
    channel: () => { const c = { on: () => c, subscribe: () => c, unsubscribe() {} }; return c; }, removeChannel() {}, functions: { invoke: ok(null) },
  };
  window.supabase = { createClient: () => client };
})();
