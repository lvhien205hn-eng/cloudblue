-- =====================================================================================================================
-- CloudBlue SQL v28 (ĐÃ GỒM v27) — 💎 TÍCH BLUE + 🤖 ĐỔI ANDROID XOÁ MÁY CŨ TRƯỚC + 🧹 DỌN MÁY ĐỔI ANDROID       10/11/2026
--   Chưa chạy v27 cũng được: file này làm luôn phần v27. Đã chạy v27 rồi: chạy file này vẫn đúng (chạy lại nhiều lần được).
--
-- 🤖 ĐỔI ANDROID (từ v28): khách bấm Đổi → máy cũ chuyển "đang xoá" NGAY (không mở / điều khiển được nữa), máy chủ xoá sạch
--      máy cũ + dữ liệu XONG thì máy mới mới được tạo (máy mới chờ ở trạng thái "Đang tạo", máy chủ ghi 'wait-old').
--      → khách KHÔNG BAO GIỜ dùng được 2 máy cùng lúc. Máy chủ giữ máy cũ đang mất kết nối → máy mới tạo ngay, máy cũ bị
--        xoá khi máy chủ đó bật lại. Máy mới tạo lỗi (máy cũ đã xoá) → tự tạo lại tối đa 3 lần ở máy chủ còn chỗ;
--        vẫn lỗi → báo lỗi, admin bấm 🔁 Tạo lại (không mất hạn của khách).
-- 🧹 DỌN MÁY ĐỔI ANDROID (admin → ĐT đám mây): admin_switch_info() xem số máy · admin_switch_cleanup() xoá sạch máy cũ còn
--      sót (máy chủ xoá máy ảo, web ẩn luôn) · admin_switch_retry(id) tạo lại máy mới bị lỗi / kẹt.
--
-- 💎 TÍCH BLUE (v27, 1 Blue = 1đ)
--   NHẬN  · Điểm danh mỗi ngày +50 (đủ 7 ngày liền thưởng thêm +150)
--         · Bạn được mời NẠP TIỀN hoặc MUA lần đầu → người mời +500 (1 lần / 1 bạn)
--         · Mỗi đơn trả bằng TIỀN (thuê / gia hạn / nâng cấp máy, mua hàng) hoàn 2% thành Blue (phần trả bằng Blue không hoàn)
--   DÙNG  · Trả tiền THUÊ hoặc GIA HẠN máy đám mây bằng Blue: tối đa 100% đơn; thiếu Blue thì phần còn lại trừ số dư
--         · Máy tạo lỗi → hoàn lại cả tiền lẫn Blue; Blue hoàn của đơn đó bị thu lại
--   NHIỆM VỤ HẰNG NGÀY (mỗi ngày 1 lần): mở máy đám mây +20 · chia sẻ link mời +20 · mời 1 bạn đăng ký +50 (+ điểm danh ở trên)
--   CHỐNG ẢO · Chỉ tài khoản đã NẠP TIỀN ít nhất 1 lần mới DÙNG được Blue (vẫn tích được)
--            · 1 mạng (IP) tối đa 3 tài khoản điểm danh mỗi ngày
--   Mọi con số chỉnh ở web admin → 🎁 Khuyến mãi → 💎 Tích Blue (bảng blue_settings, KHÔNG đụng settings của web).
-- Cả file là 1 giao dịch: lỗi ở đâu → không đổi gì. Dòng cuối phải ra: v28 xong | 1 | 3 | 11 | 6 | 3 | 1
-- =====================================================================================================================
begin;

-- ---------- 1) CỘT + BẢNG ----------
alter table public.profiles add column if not exists blue bigint not null default 0;
do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'profiles_blue_nonneg') then
    alter table public.profiles add constraint profiles_blue_nonneg check (blue >= 0);
  end if;
end $$;
alter table public.cloud_phones add column if not exists blue_paid bigint not null default 0;    -- Blue khách dùng trả máy này
alter table public.cp_sales add column if not exists blue bigint not null default 0;             -- Blue dùng trong lượt bán (amount = tiền thật)

create table if not exists public.blue_settings (
  id         int primary key default 1 check (id = 1),
  data       jsonb not null default '{}',
  updated_at timestamptz not null default now()
);
insert into public.blue_settings(id) values (1) on conflict do nothing;
alter table public.blue_settings enable row level security;
revoke all on public.blue_settings from anon, authenticated;

create table if not exists public.blue_ledger (
  id         bigserial primary key,
  created_at timestamptz not null default now(),
  user_id    uuid not null references public.profiles(id) on delete cascade,
  delta      bigint not null,
  kind       text not null check (kind in ('checkin', 'streak', 'task', 'ref', 'cashback', 'spend', 'refund', 'admin', 'clawback')),
  ref        text,
  note       text,
  after      bigint
);
create index if not exists blue_ledger_user on public.blue_ledger (user_id, created_at desc);
create index if not exists blue_ledger_time on public.blue_ledger (created_at desc);
create unique index if not exists blue_ledger_once on public.blue_ledger (kind, ref) where kind in ('ref', 'cashback', 'clawback') and ref is not null;
alter table public.blue_ledger enable row level security;
drop policy if exists "blue own or admin read" on public.blue_ledger;
create policy "blue own or admin read" on public.blue_ledger for select using (user_id = auth.uid() or is_admin());
revoke insert, update, delete, truncate on public.blue_ledger from anon, authenticated;

create table if not exists public.blue_checkins (
  user_id    uuid not null references public.profiles(id) on delete cascade,
  day        date not null,
  ip         text,
  streak     int not null default 1,
  got        bigint not null default 0,
  created_at timestamptz not null default now(),
  primary key (user_id, day)
);
create index if not exists blue_checkins_ip on public.blue_checkins (day, ip);

-- nhiệm vụ hằng ngày đã nhận (mỗi nhiệm vụ 1 lần / ngày)
create table if not exists public.blue_tasks (
  user_id    uuid not null references public.profiles(id) on delete cascade,
  day        date not null,
  task       text not null check (task in ('play', 'share', 'invite')),
  ip         text,
  got        bigint not null default 0,
  created_at timestamptz not null default now(),
  primary key (user_id, day, task)
);
create index if not exists blue_tasks_ip on public.blue_tasks (day, task, ip);
alter table public.blue_tasks enable row level security;
drop policy if exists "task own or admin read" on public.blue_tasks;
create policy "task own or admin read" on public.blue_tasks for select using (user_id = auth.uid() or is_admin());
revoke insert, update, delete, truncate on public.blue_tasks from anon, authenticated;
alter table public.blue_checkins enable row level security;
drop policy if exists "checkin own or admin read" on public.blue_checkins;
create policy "checkin own or admin read" on public.blue_checkins for select using (user_id = auth.uid() or is_admin());
revoke insert, update, delete, truncate on public.blue_checkins from anon, authenticated;

-- ---------- 2) TIỆN ÍCH ----------
-- cấu hình: mặc định + chỗ admin đã đổi
create or replace function public._blue_cfg() returns jsonb
language sql stable security definer set search_path = public as $$
  select jsonb_build_object('on', true, 'checkin', 50, 'streak_days', 7, 'streak_bonus', 150, 'ref', 500,
                            'cashback', 2, 'ip_max', 3, 'need_topup', true, 'max_pct', 100,
                            'task_play', 20, 'task_share', 20, 'task_invite', 50)
         || coalesce((select case when jsonb_typeof(data) = 'object' then data end from blue_settings where id = 1), '{}'::jsonb)
$$;

-- ngày theo giờ Việt Nam (điểm danh qua 0 giờ VN là ngày mới)
create or replace function public._blue_today() returns date
language sql stable as $$ select (now() at time zone 'Asia/Ho_Chi_Minh')::date $$;

-- IP người gọi (Supabase chuyển header của yêu cầu vào request.headers); không có → null (không giới hạn theo IP)
create or replace function public._blue_ip() returns text
language plpgsql stable as $$
declare h json; v text;
begin
  begin h := nullif(current_setting('request.headers', true), '')::json; exception when others then return null; end;
  if h is null then return null; end if;
  v := coalesce(nullif(trim(h->>'cf-connecting-ip'), ''), nullif(trim(h->>'x-real-ip'), ''),
                nullif(trim(split_part(coalesce(h->>'x-forwarded-for', ''), ',', 1)), ''));
  return left(v, 64);
end $$;

-- cộng / trừ Blue + ghi lịch sử (không để âm; lượt 'ref' / 'cashback' / 'clawback' cùng mã chỉ tính 1 lần)
create or replace function public._blue_add(p_user uuid, p_delta bigint, p_kind text, p_ref text, p_note text)
returns bigint language plpgsql security definer set search_path = public as $$
declare v bigint; d bigint; n int;
begin
  if p_user is null or coalesce(p_delta, 0) = 0 then return 0; end if;
  select blue into v from profiles where id = p_user for update;
  if not found then return 0; end if;
  d := greatest(p_delta, -v);
  if d = 0 then return 0; end if;
  insert into blue_ledger(user_id, delta, kind, ref, note, after) values (p_user, d, p_kind, p_ref, left(p_note, 200), v + d)
  on conflict do nothing;
  get diagnostics n = row_count;
  if n = 0 then return 0; end if;
  update profiles set blue = v + d where id = p_user;
  return d;
end $$;

-- được DÙNG Blue chưa (đã nạp tiền ít nhất 1 lần — admin luôn được)
create or replace function public._blue_can_use(p_user uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select coalesce((_blue_cfg()->>'on')::boolean, true)
     and (not coalesce((_blue_cfg()->>'need_topup')::boolean, true)
          or exists (select 1 from topups where user_id = p_user and status = 'done')
          or exists (select 1 from profiles where id = p_user and role = 'admin'))
$$;

-- số Blue sẽ dùng cho đơn p_total (kiểm điều kiện; CHƯA trừ)
create or replace function public._blue_take(p_user uuid, p_total bigint) returns bigint
language plpgsql security definer set search_path = public as $$
declare c jsonb := _blue_cfg(); v bigint; pct int;
begin
  if not coalesce((c->>'on')::boolean, true) then raise exception 'BLUE_OFF'; end if;
  if not _blue_can_use(p_user) then raise exception 'BLUE_NEED_TOPUP'; end if;
  select blue into v from profiles where id = p_user;
  pct := least(greatest(coalesce((c->>'max_pct')::int, 100), 0), 100);
  v := least(coalesce(v, 0), floor(greatest(p_total, 0) * pct / 100.0)::bigint);
  if v <= 0 then raise exception 'BLUE_EMPTY'; end if;
  return v;
end $$;

-- thưởng người mời khi bạn NẠP / MUA lần đầu (1 lần / 1 bạn)
create or replace function public._blue_ref_bonus(p_user uuid) returns void
language plpgsql security definer set search_path = public as $$
declare c jsonb := _blue_cfg(); me profiles; amt bigint;
begin
  if p_user is null or not coalesce((c->>'on')::boolean, true) then return; end if;
  amt := coalesce((c->>'ref')::bigint, 0);
  if amt <= 0 then return; end if;
  select * into me from profiles where id = p_user;
  if not found or me.ref_by is null or me.ref_by = me.id then return; end if;
  if exists (select 1 from profiles where id = me.ref_by and locked) then return; end if;
  perform _blue_add(me.ref_by, amt, 'ref', 'ref:' || me.id, 'Bạn ' || left(me.username, 3) || '*** nạp / mua lần đầu');
end $$;

-- hoàn Blue % theo số TIỀN khách trả
create or replace function public._blue_cashback(p_user uuid, p_amount bigint, p_ref text, p_note text) returns void
language plpgsql security definer set search_path = public as $$
declare c jsonb := _blue_cfg(); pct numeric; amt bigint;
begin
  if p_user is null or coalesce(p_amount, 0) <= 0 or not coalesce((c->>'on')::boolean, true) then return; end if;
  pct := coalesce((c->>'cashback')::numeric, 0);
  if pct <= 0 then return; end if;
  amt := floor(p_amount * pct / 100.0)::bigint;
  if amt > 0 then perform _blue_add(p_user, amt, 'cashback', p_ref, p_note); end if;
end $$;

-- ---------- 3) TỰ ĐỘNG: hoàn Blue khi mua · thưởng người mời · thu lại khi hoàn tiền ----------
create or replace function public._blue_on_sale() returns trigger
language plpgsql security definer set search_path = public as $$
declare v bigint;
begin
  begin
    if new.user_id is not null and new.kind in ('new', 'renew', 'upgrade') and coalesce(new.amount, 0) > 0 then
      perform _blue_cashback(new.user_id, new.amount, 'cps:' || new.id,
                             case new.kind when 'new' then 'Hoàn Blue: thuê máy' when 'renew' then 'Hoàn Blue: gia hạn máy' else 'Hoàn Blue: nâng cấp máy' end);
      perform _blue_ref_bonus(new.user_id);
    elsif new.kind = 'refund' and new.user_id is not null and new.phone_id is not null then
      select coalesce(sum(l.delta), 0) into v from blue_ledger l join cp_sales s on l.ref = 'cps:' || s.id
       where l.kind = 'cashback' and s.phone_id = new.phone_id and s.kind = 'new';
      if v > 0 then perform _blue_add(new.user_id, -v, 'clawback', 'cpsr:' || new.id, 'Thu lại Blue hoàn (máy tạo lỗi đã hoàn tiền)'); end if;
    end if;
  exception when others then
    raise warning 'Blue (cp_sales %) bỏ qua: %', new.id, sqlerrm;          -- không bao giờ làm hỏng lượt mua của khách
  end;
  return null;
end $$;
drop trigger if exists blue_on_sale on public.cp_sales;
create trigger blue_on_sale after insert on public.cp_sales for each row execute function public._blue_on_sale();

create or replace function public._blue_on_order() returns trigger
language plpgsql security definer set search_path = public as $$
declare v bigint;
begin
  begin
    if new.user_id is not null and new.status = 'done' and coalesce(new.total, 0) > 0
       and (tg_op = 'INSERT' or old.status is distinct from 'done') then
      perform _blue_cashback(new.user_id, new.total, 'ord:' || new.id, 'Hoàn Blue: mua ' || left(coalesce(new.product_name, 'hàng'), 60));
      perform _blue_ref_bonus(new.user_id);
    elsif tg_op = 'UPDATE' and old.status = 'done' and new.status is distinct from 'done' and new.user_id is not null then
      select coalesce(sum(delta), 0) into v from blue_ledger where kind = 'cashback' and ref = 'ord:' || new.id;
      if v > 0 then perform _blue_add(new.user_id, -v, 'clawback', 'ordr:' || new.id, 'Thu lại Blue hoàn (đơn đã hoàn tiền)'); end if;
    end if;
  exception when others then
    raise warning 'Blue (đơn %) bỏ qua: %', new.id, sqlerrm;
  end;
  return null;
end $$;
drop trigger if exists blue_on_order on public.orders;
create trigger blue_on_order after insert or update of status on public.orders for each row execute function public._blue_on_order();

create or replace function public._blue_on_topup() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  begin
    if new.status = 'done' and (tg_op = 'INSERT' or old.status is distinct from 'done') then perform _blue_ref_bonus(new.user_id); end if;
  exception when others then
    raise warning 'Blue (nạp %) bỏ qua: %', new.id, sqlerrm;
  end;
  return null;
end $$;
drop trigger if exists blue_on_topup on public.topups;
create trigger blue_on_topup after insert or update of status on public.topups for each row execute function public._blue_on_topup();

-- ---------- 4) KHÁCH: xem · điểm danh · nhiệm vụ hằng ngày ----------
-- có máy đám mây đang chạy (của mình hoặc được chia sẻ)
create or replace function public._blue_has_phone(p_user uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from cloud_phones p where p.status = 'active' and p.user_id = p_user)
      or exists (select 1 from cloud_phone_shares s join cloud_phones p on p.id = s.phone_id
                  where s.grantee_id = p_user and s.kind = 'share' and not s.revoked and (s.expires_at is null or s.expires_at > now())
                    and p.status = 'active')
$$;
-- hôm nay có bạn nào đăng ký / nhận lời mời của mình chưa
create or replace function public._blue_invited_today(p_user uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from profiles f where f.ref_by = p_user and f.id <> p_user
                    and (coalesce(f.ref_at, f.created_at) at time zone 'Asia/Ho_Chi_Minh')::date = _blue_today())
$$;
create or replace function public.blue_info() returns json
language plpgsql stable security definer set search_path = public as $$
declare c jsonb := _blue_cfg(); me profiles; d date := _blue_today(); t blue_checkins; y blue_checkins; st int; sd int; nx bigint; tk json;
begin
  select * into me from profiles where id = auth.uid();
  if not found then raise exception 'NOT_LOGGED_IN'; end if;
  select * into t from blue_checkins where user_id = me.id and day = d;
  select * into y from blue_checkins where user_id = me.id and day = d - 1;
  st := case when t.user_id is not null then t.streak when y.user_id is not null then y.streak else 0 end;
  sd := coalesce((c->>'streak_days')::int, 0);
  nx := coalesce((c->>'checkin')::bigint, 0) + case when sd > 0 and (st + 1) % sd = 0 then coalesce((c->>'streak_bonus')::bigint, 0) else 0 end;
  -- nhiệm vụ hôm nay: id · Blue nhận · đã nhận chưa · đủ điều kiện nhận chưa (nhiệm vụ 0 Blue = admin tắt → không hiện)
  select coalesce(json_agg(x.o order by x.k), '[]'::json) into tk from (
    select 1 k, json_build_object('id', 'checkin', 'got', nx, 'done', t.user_id is not null, 'ready', true) o where nx > 0
    union all
    select 2, json_build_object('id', 'play', 'got', (c->>'task_play')::bigint,
                                'done', exists (select 1 from blue_tasks b where b.user_id = me.id and b.day = d and b.task = 'play'),
                                'ready', _blue_has_phone(me.id))
     where coalesce((c->>'task_play')::bigint, 0) > 0
    union all
    select 3, json_build_object('id', 'share', 'got', (c->>'task_share')::bigint,
                                'done', exists (select 1 from blue_tasks b where b.user_id = me.id and b.day = d and b.task = 'share'), 'ready', true)
     where coalesce((c->>'task_share')::bigint, 0) > 0
    union all
    select 4, json_build_object('id', 'invite', 'got', (c->>'task_invite')::bigint,
                                'done', exists (select 1 from blue_tasks b where b.user_id = me.id and b.day = d and b.task = 'invite'),
                                'ready', _blue_invited_today(me.id))
     where coalesce((c->>'task_invite')::bigint, 0) > 0) x;
  return json_build_object(
    'on', coalesce((c->>'on')::boolean, true),
    'blue', me.blue,
    'can_use', _blue_can_use(me.id),
    'need_topup', coalesce((c->>'need_topup')::boolean, true),
    'today', t.user_id is not null,
    'streak', st,
    'next_got', nx,
    'tasks', tk,
    'cfg', json_build_object('checkin', (c->>'checkin')::bigint, 'streak_days', sd, 'streak_bonus', (c->>'streak_bonus')::bigint,
                             'ref', (c->>'ref')::bigint, 'cashback', (c->>'cashback')::numeric, 'max_pct', (c->>'max_pct')::int),
    'items', coalesce((select json_agg(json_build_object('t', x.created_at, 'delta', x.delta, 'kind', x.kind, 'note', x.note) order by x.id desc)
                         from (select * from blue_ledger where user_id = me.id order by id desc limit 30) x), '[]'::json));
end $$;

create or replace function public.blue_checkin() returns json
language plpgsql security definer set search_path = public as $$
declare c jsonb := _blue_cfg(); me profiles; d date := _blue_today(); v_ip text := _blue_ip(); prev int; st int; sd int;
        got bigint; bonus bigint := 0; n int; lim int;
begin
  if not coalesce((c->>'on')::boolean, true) then raise exception 'BLUE_OFF'; end if;
  select * into me from profiles where id = auth.uid() for update;
  if not found then raise exception 'NOT_LOGGED_IN'; end if;
  if me.locked then raise exception 'LOCKED'; end if;
  if exists (select 1 from blue_checkins where user_id = me.id and day = d) then raise exception 'BLUE_DONE'; end if;
  lim := coalesce((c->>'ip_max')::int, 0);
  if v_ip is not null and lim > 0 and (select count(*) from blue_checkins where day = d and ip = v_ip) >= lim then
    raise exception 'BLUE_IP_LIMIT';
  end if;
  select streak into prev from blue_checkins where user_id = me.id and day = d - 1;
  st := coalesce(prev, 0) + 1;
  sd := coalesce((c->>'streak_days')::int, 0);
  got := greatest(coalesce((c->>'checkin')::bigint, 0), 0);
  if sd > 0 and st % sd = 0 then bonus := greatest(coalesce((c->>'streak_bonus')::bigint, 0), 0); end if;
  insert into blue_checkins(user_id, day, ip, streak, got) values (me.id, d, v_ip, st, got + bonus) on conflict do nothing;
  get diagnostics n = row_count;
  if n = 0 then raise exception 'BLUE_DONE'; end if;
  if got > 0 then perform _blue_add(me.id, got, 'checkin', 'ci:' || d, 'Điểm danh ' || to_char(d, 'DD/MM')); end if;
  if bonus > 0 then perform _blue_add(me.id, bonus, 'streak', 'st:' || d, 'Thưởng ' || sd || ' ngày điểm danh liền'); end if;
  return json_build_object('ok', true, 'got', got, 'bonus', bonus, 'streak', st, 'blue', (select blue from profiles where id = me.id));
end $$;

-- nhận Blue nhiệm vụ hằng ngày: 'play' (mở máy — app / web tự gọi khi vào điều khiển máy) · 'share' (bấm chia sẻ link mời)
--                              · 'invite' (hôm nay có bạn đăng ký qua link / mã mời)
create or replace function public.blue_task(p_task text) returns json
language plpgsql security definer set search_path = public as $$
declare c jsonb := _blue_cfg(); me profiles; d date := _blue_today(); v_ip text := _blue_ip(); t text := lower(trim(coalesce(p_task, '')));
        amt bigint; n int; lim int;
begin
  if not coalesce((c->>'on')::boolean, true) then raise exception 'BLUE_OFF'; end if;
  if t not in ('play', 'share', 'invite') then raise exception 'BAD_TASK'; end if;
  amt := coalesce((c->>('task_' || t))::bigint, 0);
  if amt <= 0 then raise exception 'TASK_OFF'; end if;
  select * into me from profiles where id = auth.uid() for update;
  if not found then raise exception 'NOT_LOGGED_IN'; end if;
  if me.locked then raise exception 'LOCKED'; end if;
  if exists (select 1 from blue_tasks where user_id = me.id and day = d and task = t) then raise exception 'TASK_DONE'; end if;
  if t = 'play' and not _blue_has_phone(me.id) then raise exception 'TASK_NOT_YET'; end if;
  if t = 'invite' and not _blue_invited_today(me.id) then raise exception 'TASK_NOT_YET'; end if;
  lim := coalesce((c->>'ip_max')::int, 0);
  if t in ('share', 'invite') and v_ip is not null and lim > 0
     and (select count(*) from blue_tasks where day = d and task = t and ip = v_ip) >= lim then
    raise exception 'BLUE_IP_LIMIT';
  end if;
  insert into blue_tasks(user_id, day, task, ip, got) values (me.id, d, t, v_ip, amt) on conflict do nothing;
  get diagnostics n = row_count;
  if n = 0 then raise exception 'TASK_DONE'; end if;
  perform _blue_add(me.id, amt, 'task', null, case t when 'play' then 'Nhiệm vụ: mở máy đám mây'
                                                       when 'share' then 'Nhiệm vụ: chia sẻ link mời' else 'Nhiệm vụ: mời bạn đăng ký' end);
  return json_build_object('ok', true, 'task', t, 'got', amt, 'blue', (select blue from profiles where id = me.id));
end $$;

-- ---------- 5) TRẢ BẰNG BLUE: thuê máy (thêm p_blue) ----------
drop function if exists public.cloudphone_order_custom(integer, integer, integer, text, text, integer, integer, text, boolean, text);
create or replace function public.cloudphone_order_custom(p_ram integer, p_cpu integer, p_days integer, p_res text default '720x1280'::text,
  p_name text default null::text, p_fps integer default 30, p_qty integer default 1, p_android text default '9'::text,
  p_free boolean default false, p_promo text default null, p_blue boolean default false)
returns cloud_phones language plpgsql security definer set search_path = public as $$
declare v_android text; me profiles; pr cloudphone_pricing; total bigint; row cloud_phones; first cloud_phones;
        v_res text; w int; h int; v_fps int; st json; i int; v_base text; v_days int; v_used int;
        unit bigint; unit_ctv bigint; c promo_codes; v_disc bigint := 0; v_red bigint; each bigint; v_paid bigint;
        v_blue bigint := 0; v_left bigint := 0; v_bp bigint;
begin
  perform _app_gate();
  select * into me from profiles where id = auth.uid() for update;
  if not found then raise exception 'NOT_LOGGED_IN'; end if;
  if me.locked then raise exception 'LOCKED'; end if;
  select * into pr from cloudphone_pricing where id = 1;
  v_android := coalesce(nullif(trim(p_android), ''), '9');
  if not (v_android = any(string_to_array(replace(coalesce(pr.android_versions, '9'), ' ', ''), ','))) then raise exception 'BAD_ANDROID'; end if;
  st := cloudphone_status(v_android);
  if (st->>'maint')::boolean and not is_admin() then raise exception 'MAINTENANCE'; end if;
  if not (st->>'online')::boolean then raise exception 'SERVER_OFFLINE'; end if;
  if p_qty is null or p_qty < 1 or p_qty > 20 then raise exception 'BAD_QTY'; end if;
  if coalesce(pr.max_per_user, 0) > 0 and not is_admin() then
    select count(*) into v_used from cloud_phones
    where user_id = me.id and status in ('pending', 'creating', 'active', 'expired', 'cancelling');
    if v_used + p_qty > pr.max_per_user then raise exception 'MAX_PER_USER'; end if;
  end if;
  if p_ram * p_qty > (st->>'free_ram')::numeric or p_cpu * p_qty > (st->>'free_cpu')::numeric then raise exception 'OUT_OF_CAPACITY'; end if;

  select * into pr from cloudphone_pricing where id = 1 for update;
  if pr.stock is not null and pr.stock < p_qty and not is_admin() then raise exception 'OUT_OF_STOCK'; end if;
  if p_ram is null or p_ram < pr.min_ram or p_ram > _and_max(pr, v_android, 'ram') then raise exception 'BAD_RAM'; end if;
  if p_cpu is null or p_cpu < pr.min_cpu or p_cpu > _and_max(pr, v_android, 'cpu') then raise exception 'BAD_CPU'; end if;
  v_days := p_days;
  if coalesce(p_free, false) then
    if _promo_norm(p_promo) is not null then raise exception 'PROMO_NOT_FOR_FREE'; end if;
    if coalesce(p_blue, false) then raise exception 'BLUE_NOT_FOR_FREE'; end if;
    if not pr.free_on and not is_admin() then raise exception 'FREE_OFF'; end if;
    if pr.free_until is not null and now() > pr.free_until and not is_admin() then raise exception 'FREE_OFF'; end if;
    if (p_ram > pr.free_max_ram or p_cpu > pr.free_max_cpu) and not is_admin() then raise exception 'FREE_LIMIT'; end if;
    if p_qty <> 1 and not is_admin() then raise exception 'FREE_ONE'; end if;
    select count(*) into v_used from cloud_phones
    where user_id = me.id and is_free and created_at >= coalesce(pr.free_since, '-infinity'::timestamptz);
    if v_used >= 1 and not is_admin() then raise exception 'FREE_USED'; end if;
    v_days := greatest(pr.free_days, 1);
  elsif v_days is null or v_days < pr.min_days or v_days > pr.max_days then raise exception 'BAD_DAYS'; end if;
  v_fps := coalesce(p_fps, 30);
  if v_fps < pr.min_fps or v_fps > pr.max_fps then raise exception 'BAD_FPS'; end if;
  if v_fps > 60 and p_cpu < 4 then raise exception 'FPS_TOO_HIGH'; end if;
  v_res := lower(regexp_replace(coalesce(p_res, ''), '\s', '', 'g'));
  if v_res = '' then v_res := '720x1280'; end if;
  if v_res !~ '^[0-9]{3,4}x[0-9]{3,4}$' then raise exception 'BAD_RES'; end if;
  w := split_part(v_res, 'x', 1)::int; h := split_part(v_res, 'x', 2)::int;
  if w < 320 or h < 320 or w > 4096 or h > 4096 then raise exception 'BAD_RES'; end if;

  -- GIÁ: giá gốc → giá CTV; có mã → so với giá sau mã, lấy mức RẺ HƠN (không cộng dồn). Mã không lợi hơn CTV → KHÔNG tính lượt.
  if coalesce(p_free, false) then unit := 0; unit_ctv := 0; total := 0;
  else
    unit := _cp_unit_base(pr, p_ram, p_cpu, v_days);
    unit_ctv := _ctv_price(me.id, unit);
    total := unit_ctv * p_qty;
    if _promo_norm(p_promo) is not null then
      c := _promo_get(p_promo, me.id, 'cp_new', unit * p_qty);
      v_disc := _promo_amount(c, unit * p_qty);
      if unit * p_qty - v_disc < total then total := unit * p_qty - v_disc; else c := null; v_disc := 0; end if;
    end if;
  end if;
  -- 💎 TRẢ BẰNG BLUE: dùng Blue trước (tối đa max_pct % đơn), thiếu thì phần còn lại trừ số dư
  if coalesce(p_blue, false) and total > 0 then v_blue := _blue_take(me.id, total); end if;
  if me.balance < total - v_blue then raise exception 'INSUFFICIENT_BALANCE'; end if;
  update profiles set balance = balance - (total - v_blue) where id = me.id;
  if pr.stock is not null then update cloudphone_pricing set stock = greatest(stock - p_qty, 0) where id = 1; end if;
  if c.id is not null then v_red := _promo_use(c.id, me.id, 'cp_new', unit * p_qty, v_disc, total, null); end if;
  each := case when v_red is not null then total / p_qty else unit_ctv end;           -- tiền từng máy (hoàn tiền từng máy khi tạo lỗi)
  v_base := left(coalesce(nullif(trim(p_name), ''), case when coalesce(p_free, false) then 'Máy miễn phí ' else 'Máy ' end || p_ram || 'GB'), 34);
  v_left := v_blue;
  for i in 1 .. p_qty loop
    v_paid := case when v_red is not null and i = 1 then total - each * (p_qty - 1) else each end;
    v_bp := least(v_left, v_paid); v_left := v_left - v_bp;                          -- Blue chia lần lượt cho từng máy
    insert into cloud_phones(user_id, name, ram, cpu, res, fps, days, status, paid, blue_paid, android, is_free, promo_red)
    values (me.id, case when p_qty > 1 then v_base || ' #' || i else v_base end,
            p_ram, p_cpu, v_res, v_fps, v_days, 'pending', v_paid - v_bp, v_bp, v_android, coalesce(p_free, false), v_red)
    returning * into row;
    if i = 1 then first := row; end if;
  end loop;
  if v_red is not null then update promo_redemptions set ref_id = first.id::text where id = v_red; end if;
  if v_blue > 0 then
    perform _blue_add(me.id, -v_blue, 'spend', 'cpn:' || first.id,
                      'Thuê ' || case when p_qty > 1 then p_qty || ' máy ' else 'máy ' end || p_ram || 'GB · ' || v_days || ' ngày');
  end if;
  return first;
end $$;

-- ---------- 6) TRẢ BẰNG BLUE: gia hạn (thêm p_blue) ----------
drop function if exists public.cloudphone_renew(uuid, integer, text);
create or replace function public.cloudphone_renew(p_id uuid, p_days integer, p_promo text default null, p_blue boolean default false)
returns cloud_phones language plpgsql security definer set search_path = public as $function$
declare me profiles; m cloud_phones; pr cloudphone_pricing; price bigint; v_off timestamptz; base bigint; c promo_codes; v_disc bigint := 0;
        v_blue bigint := 0;
begin
  perform _app_gate();
  select * into me from profiles where id = auth.uid() for update;
  if not found then raise exception 'NOT_LOGGED_IN'; end if;
  if me.locked then raise exception 'LOCKED'; end if;
  if (cloudphone_status()->>'maint')::boolean and not is_admin() then raise exception 'MAINTENANCE'; end if;
  select * into pr from cloudphone_pricing where id = 1;
  v_off := greatest(pr.maint_off_at, (select nullif(data->>'maint_off_at', '')::timestamptz from settings where id = 1));
  select * into m from cloud_phones where id = p_id and user_id = me.id for update;
  if not found then raise exception 'NO_PHONE'; end if;
  if m.is_free then raise exception 'FREE_NO_RENEW'; end if;
  if m.locked and (m.locked_until is null or m.locked_until > now()) then raise exception 'PHONE_LOCKED'; end if;
  if m.status not in ('active', 'expired')
     or (m.status = 'expired' and m.expires_at is not null
         and now() > greatest(m.expires_at, coalesce(v_off, m.expires_at)) + interval '30 minutes') then
    raise exception 'PHONE_GONE';
  end if;
  if _cp_switching(m) then raise exception 'SWITCHING: Máy đang đổi Android — chờ máy mới tạo xong rồi gia hạn máy mới'; end if;
  if p_days is null or p_days < 1 or p_days > pr.max_days then raise exception 'BAD_DAYS'; end if;
  base := _cp_unit_base(pr, m.ram, m.cpu, p_days);
  price := _ctv_price(me.id, base);
  if _promo_norm(p_promo) is not null then
    c := _promo_get(p_promo, me.id, 'cp_renew', base);
    v_disc := _promo_amount(c, base);
    if base - v_disc < price then price := base - v_disc; else c := null; v_disc := 0; end if;
  end if;
  if coalesce(p_blue, false) and price > 0 then v_blue := _blue_take(me.id, price); end if;     -- 💎 Blue trước, thiếu thì trừ số dư
  if me.balance < price - v_blue then raise exception 'INSUFFICIENT_BALANCE'; end if;
  update profiles set balance = balance - (price - v_blue) where id = me.id;
  if c.id is not null then perform _promo_use(c.id, me.id, 'cp_renew', base, v_disc, price, m.id::text); end if;
  update cloud_phones set pending_renew_days = pending_renew_days + p_days, updated_at = now()
  where id = m.id returning * into m;
  insert into cp_sales(user_id, phone_id, kind, android, ram, cpu, days, amount, blue, base, promo)
  values (me.id, m.id, 'renew', m.android, m.ram, m.cpu, p_days, price - v_blue, v_blue, base, case when c.id is not null then c.code end);
  if v_blue > 0 then
    perform _blue_add(me.id, -v_blue, 'spend', 'cpr:' || m.id || ':' || floor(extract(epoch from clock_timestamp()) * 1000)::bigint,
                      'Gia hạn ' || left(m.name, 30) || ' +' || p_days || ' ngày');
  end if;
  return m;
end $function$;

-- ---------- 7) MÁY TẠO LỖI → hoàn cả tiền lẫn Blue ----------
create or replace function public.cloudphone_refund(p_id uuid, p_err text) returns void
language plpgsql security definer set search_path = public as $function$
declare m cloud_phones; v_code uuid;
begin
  select * into m from cloud_phones where id = p_id for update;
  if not found then return; end if;
  if (m.paid > 0 or coalesce(m.blue_paid, 0) > 0) and m.status in ('pending', 'error') then
    if m.paid > 0 then update profiles set balance = balance + m.paid where id = m.user_id; end if;
    if coalesce(m.blue_paid, 0) > 0 then perform _blue_add(m.user_id, m.blue_paid, 'refund', 'cpref:' || m.id, 'Hoàn Blue: máy tạo lỗi'); end if;
    update cloudphone_pricing set stock = stock + 1 where id = 1 and stock is not null;
  elsif m.paid = 0 and coalesce(m.blue_paid, 0) = 0 and m.promo_red is not null and m.status in ('pending', 'creating') then
    update cloudphone_pricing set stock = stock + 1 where id = 1 and stock is not null;          -- máy tặng
  end if;
  update cloud_phones set status = 'error', paid = 0, blue_paid = 0, updated_at = now(),
    error = left(coalesce(p_err, 'Lỗi tạo máy') || case when m.paid > 0 and coalesce(m.blue_paid, 0) > 0 then ' — đã hoàn ' || m.paid || 'đ vào số dư và ' || m.blue_paid || ' Blue.'
                                                       when m.paid > 0 then ' — đã hoàn ' || m.paid || 'đ vào số dư.'
                                                       when coalesce(m.blue_paid, 0) > 0 then ' — đã hoàn ' || m.blue_paid || ' Blue.'
                                                       when m.promo_red is not null and m.status <> 'error' then ' — mã của bạn đã được mở lại, nhập lại để nhận máy.' else '' end, 400)
  where id = p_id;
  if m.promo_red is not null and m.status <> 'error'
     and not exists (select 1 from cloud_phones x where x.promo_red = m.promo_red and x.status <> 'error') then
    update promo_redemptions set reverted = true where id = m.promo_red and not reverted returning code_id into v_code;
    if v_code is not null then update promo_codes set used = greatest(used - 1, 0), updated_at = now() where id = v_code; end if;
  end if;
end $function$;

-- lịch sử bán: máy mới ghi cả Blue (máy trả trọn bằng Blue + có mã không còn bị hiểu nhầm là "máy tặng")
create or replace function public._cp_after_insert() returns trigger
language plpgsql security definer set search_path = public as $function$
begin
  insert into cp_sales(created_at, user_id, phone_id, kind, android, ram, cpu, days, amount, blue)
  values (new.created_at, new.user_id, new.id,
          case when new.replaces is not null then 'switch'
               when new.is_free then 'free'
               when new.promo_red is not null and coalesce(new.paid, 0) = 0 and coalesce(new.blue_paid, 0) = 0 then 'gift'
               else 'new' end,
          new.android, new.ram, new.cpu, new.days, coalesce(new.paid, 0), coalesce(new.blue_paid, 0));
  return null;
end $function$;

-- sau khi đổi trạng thái: · máy MỚI (đổi Android) chạy xong → (kiểu cũ trước v28) xoá máy cũ còn chạy song song
--                         · máy CŨ đã xoá xong trên máy chủ (cancelled) → máy mới đang chờ ('wait-old') được tạo NGAY
--                         · hoàn tiền (máy tạo lỗi) → ghi lịch sử số âm, cả phần Blue
create or replace function public._cp_after_update() returns trigger
language plpgsql security definer set search_path = public as $function$
begin
  if new.replaces is not null and old.status is distinct from new.status and old.status in ('pending', 'creating') then
    if new.status = 'active' then
      update cloud_phone_shares set phone_id = new.id where phone_id = new.replaces;
      update cloud_phones
         set status = 'cancelling', switch_to = new.id, updated_at = now(),
             error = 'Đã đổi sang Android ' || coalesce(new.android, '?') || ' — máy cũ và dữ liệu cũ tự xoá.'
       where id = new.replaces and status not in ('cancelling', 'cancelled');
    elsif new.status in ('cancelling', 'cancelled', 'error') then
      update cloud_phones                       -- chỉ khi máy cũ CÒN chạy (đổi kiểu cũ) mới mở lại cho khách đổi lần sau
         set switch_to = null, updated_at = now(),
             error = left('Đổi Android chưa được (' || coalesce(nullif(new.error, ''), 'máy chủ bận') || ') — máy vẫn giữ nguyên, thử lại sau.', 400)
       where id = new.replaces and switch_to = new.id and status in ('active', 'expired');
    end if;
  end if;
  if new.switch_to is not null and new.status = 'cancelled' and old.status is distinct from 'cancelled' then
    update cloud_phones set node = null, created_at = now(), updated_at = now()
     where id = new.switch_to and replaces = new.id and status = 'pending' and node = 'wait-old';
  end if;
  if (coalesce(old.paid, 0) > 0 or coalesce(old.blue_paid, 0) > 0)
     and coalesce(new.paid, 0) = 0 and coalesce(new.blue_paid, 0) = 0 and new.status = 'error' then
    insert into cp_sales(user_id, phone_id, kind, android, ram, cpu, days, amount, blue, note)
    values (new.user_id, new.id, 'refund', new.android, new.ram, new.cpu, new.days, -coalesce(old.paid, 0), -coalesce(old.blue_paid, 0),
            left(coalesce(new.error, ''), 300));
  end if;
  return null;
end $function$;

-- ---------- 8) ADMIN ----------
create or replace function public.admin_blue_set(p jsonb) returns jsonb
language plpgsql security definer set search_path = public as $$
declare o jsonb;
begin
  if not is_admin() then raise exception 'NOT_ADMIN'; end if;
  p := coalesce(p, '{}'::jsonb);
  o := jsonb_build_object(
    'on',           coalesce((p->>'on')::boolean, true),
    'checkin',      least(greatest(coalesce((p->>'checkin')::bigint, 50), 0), 100000),
    'streak_days',  least(greatest(coalesce((p->>'streak_days')::int, 7), 0), 365),
    'streak_bonus', least(greatest(coalesce((p->>'streak_bonus')::bigint, 150), 0), 1000000),
    'ref',          least(greatest(coalesce((p->>'ref')::bigint, 500), 0), 1000000),
    'cashback',     least(greatest(coalesce((p->>'cashback')::numeric, 2), 0), 50),
    'ip_max',       least(greatest(coalesce((p->>'ip_max')::int, 3), 0), 1000),
    'need_topup',   coalesce((p->>'need_topup')::boolean, true),
    'max_pct',      least(greatest(coalesce((p->>'max_pct')::int, 100), 0), 100),
    'task_play',    least(greatest(coalesce((p->>'task_play')::bigint, 20), 0), 100000),
    'task_share',   least(greatest(coalesce((p->>'task_share')::bigint, 20), 0), 100000),
    'task_invite',  least(greatest(coalesce((p->>'task_invite')::bigint, 50), 0), 100000));
  update blue_settings set data = o, updated_at = now() where id = 1;
  return o;
end $$;

-- cộng / trừ Blue tay cho 1 khách (tên đăng nhập hoặc email)
create or replace function public.admin_blue_add(p_who text, p_delta bigint, p_note text default null) returns json
language plpgsql security definer set search_path = public as $$
declare u profiles; d bigint;
begin
  if not is_admin() then raise exception 'NOT_ADMIN'; end if;
  if p_delta is null or p_delta = 0 or abs(p_delta) > 100000000 then raise exception 'BAD_AMOUNT'; end if;
  select * into u from profiles where lower(username) = lower(trim(p_who)) or lower(email) = lower(trim(p_who)) order by created_at limit 1;
  if not found then raise exception 'NO_USER'; end if;
  d := _blue_add(u.id, p_delta, 'admin', null, coalesce(nullif(trim(p_note), ''), 'Admin điều chỉnh'));
  return json_build_object('user', u.username, 'delta', d, 'blue', (select blue from profiles where id = u.id));
end $$;

create or replace function public.admin_blue_stats() returns json
language plpgsql stable security definer set search_path = public as $$
begin
  if not is_admin() then raise exception 'NOT_ADMIN'; end if;
  return json_build_object(
    'cfg', _blue_cfg(),
    'outstanding', (select coalesce(sum(blue), 0) from profiles),
    'holders', (select count(*) from profiles where blue > 0),
    'checkins_today', (select count(*) from blue_checkins where day = _blue_today()),
    'tasks_today', (select coalesce(json_object_agg(task, n), '{}'::json) from (select task, count(*) n from blue_tasks where day = _blue_today() group by task) x),
    'd30', (select coalesce(json_object_agg(kind, s), '{}'::json) from (select kind, sum(delta) s from blue_ledger where created_at > now() - interval '30 days' group by kind) x),
    'all', (select coalesce(json_object_agg(kind, s), '{}'::json) from (select kind, sum(delta) s from blue_ledger group by kind) x),
    'top', (select coalesce(json_agg(json_build_object('user', username, 'blue', blue) order by blue desc), '[]'::json)
              from (select username, blue from profiles where blue > 0 order by blue desc limit 10) t));
end $$;

-- ---------- 10) 🤖 ĐỔI ANDROID: XOÁ MÁY CŨ TRƯỚC, TẠO MÁY MỚI SAU (v28) ----------
-- Máy mới chờ máy cũ bị xoá: status 'pending' + node 'wait-old' → mọi bản cloudphoned (cả bản cũ) đều KHÔNG nhận đơn này
-- (đơn đã có tên máy chủ khác). Máy cũ xoá xong (cancelled) → trigger _cp_after_update bỏ 'wait-old' → máy chủ còn chỗ nhận ngay.
alter table public.cloud_phones add column if not exists sw_try int not null default 0;   -- máy mới (đổi Android): số lần đã tự tạo lại

create or replace function public.cloudphone_switch_android(p_id uuid, p_android text)
returns json language plpgsql security definer set search_path = public as $function$
declare me profiles; m cloud_phones; pr cloudphone_pricing; st json; v text; n int; r int; c int; nw cloud_phones; left_s numeric; v_wait boolean;
begin
  perform _app_gate();
  select * into me from profiles where id = auth.uid() for update;
  if not found then raise exception 'NOT_LOGGED_IN'; end if;
  if me.locked then raise exception 'LOCKED'; end if;
  select * into m from cloud_phones where id = p_id and user_id = me.id for update;
  if not found then raise exception 'NO_PHONE'; end if;
  if m.locked and (m.locked_until is null or m.locked_until > now()) then raise exception 'PHONE_LOCKED'; end if;
  if m.status <> 'active' or m.expires_at is null or m.expires_at <= now() then raise exception 'PHONE_NOT_ACTIVE'; end if;
  if _cp_switching(m) then raise exception 'SWITCHING: Máy đang đổi Android — chờ máy mới tạo xong (2–5 phút)'; end if;
  if m.expires_at <= now() + interval '30 minutes' then
    raise exception 'SWITCH_EXPIRING: Máy còn dưới 30 phút — gia hạn trước rồi hãy đổi Android';
  end if;
  if m.pending_ram is not null or m.pending_cpu is not null or coalesce(m.pending_renew_days, 0) > 0 then
    raise exception 'SWITCH_BUSY: Máy đang nâng cấp / gia hạn — chờ 1–2 phút rồi đổi Android';
  end if;
  select * into pr from cloudphone_pricing where id = 1;
  v := nullif(trim(coalesce(p_android, '')), '');
  if v is null or not (v = any(string_to_array(replace(coalesce(pr.android_versions, '9'), ' ', ''), ','))) then
    raise exception 'BAD_ANDROID';
  end if;
  if v = coalesce(nullif(trim(m.android), ''), '9') then raise exception 'SWITCH_SAME: Máy đang chạy Android % rồi', v; end if;
  if not is_admin() then
    select count(*) into n from cloud_phones where user_id = me.id and replaces is not null and created_at > now() - interval '24 hours';
    if n >= 3 then raise exception 'SWITCH_LIMIT: Mỗi tài khoản đổi Android tối đa 3 lần trong 24 giờ'; end if;
  end if;
  st := cloudphone_status(v);
  if (st->>'maint')::boolean and not is_admin() then raise exception 'MAINTENANCE'; end if;
  if not (st->>'online')::boolean then raise exception 'SERVER_OFFLINE'; end if;
  r := least(m.ram, _and_max(pr, v, 'ram'));
  c := least(m.cpu, _and_max(pr, v, 'cpu'));
  if r > (st->>'free_ram')::numeric or c > (st->>'free_cpu')::numeric then raise exception 'OUT_OF_CAPACITY'; end if;
  left_s := extract(epoch from (m.expires_at - now()));
  -- máy chủ giữ máy cũ đang chạy → máy mới CHỜ máy cũ bị xoá xong · máy chủ đó mất kết nối (máy cũ đằng nào cũng không dùng được)
  -- → máy mới tạo ngay, máy cũ bị xoá khi máy chủ đó bật lại
  v_wait := m.node is not null and exists (select 1 from cloud_nodes nd where nd.id = m.node and nd.updated_at > now() - interval '3 minutes');
  insert into cloud_phones(user_id, name, ram, cpu, res, fps, days, status, paid, android, is_free, replaces, until_at, node)
  values (me.id, m.name, r, c, m.res, m.fps, greatest(1, ceil(left_s / 86400.0))::int, 'pending', 0, v, m.is_free, m.id, m.expires_at,
          case when v_wait then 'wait-old' end)
  returning * into nw;
  update cloud_phone_shares set phone_id = nw.id where phone_id = m.id;           -- người được chia sẻ đi theo máy mới
  update cloud_phones set status = 'cancelling', switch_to = nw.id, updated_at = now(),
         error = 'Đổi Android: máy cũ đang bị xoá — xong tự tạo máy Android ' || v || ' (2–5 phút).'
   where id = m.id;
  return json_build_object('ok', true, 'new_id', nw.id, 'android', v, 'ram', r, 'cpu', c,
                           'reduced', (r < m.ram or c < m.cpu), 'expires_at', m.expires_at, 'delete_first', true, 'wait', v_wait);
end $function$;

-- máy mới đổi Android: chạy xong → giữ đúng hạn cũ
--   tạo lỗi · máy cũ CÒN chạy (đổi kiểu cũ trước v28) → huỷ máy mới, máy cũ giữ nguyên
--           · máy cũ ĐÃ XOÁ → không để khách trắng tay: tự tạo lại (máy chủ nào còn chỗ nhận), tối đa 3 lần; vẫn lỗi → để "Lỗi",
--             admin bấm 🔁 Tạo lại (hạn dùng của khách giữ nguyên trong until_at)
-- máy đang chờ 'wait-old' bị huỷ (khách / admin bấm Xoá) → chưa có máy ảo nào → ghi đã huỷ luôn (không máy chủ nào phải xoá)
create or replace function public._cp_switch_before() returns trigger
language plpgsql security definer set search_path = public as $function$
declare o cloud_phones;
begin
  if new.node = 'wait-old' and new.status = 'cancelling' then new.status := 'cancelled'; end if;
  if new.replaces is not null then
    if new.status = 'active' and old.status is distinct from 'active' and new.until_at is not null then
      new.expires_at := new.until_at;
      new.until_at := null;
    elsif new.status = 'error' and old.status in ('pending', 'creating') then
      select * into o from cloud_phones where id = new.replaces;
      if found and o.status in ('active', 'expired') and o.switch_to = new.id then
        new.status := case when new.node is null then 'cancelled' else 'cancelling' end;
        new.error := left('Đổi Android lỗi: ' || coalesce(new.error, ''), 400);
      elsif coalesce(new.sw_try, 0) < 3 then
        new.sw_try := coalesce(new.sw_try, 0) + 1;
        new.status := 'pending';
        if new.container is null then new.node := null; new.port := null; new.stream_url := null; end if;
        new.created_at := now(); new.updated_at := now();
        new.error := left('Đổi Android: tạo máy mới bị lỗi (' || coalesce(nullif(new.error, ''), '?') || ') — đang tự tạo lại lần ' || new.sw_try || '/3.', 400);
      else
        new.error := left('Đổi Android: chưa tạo được máy mới sau 3 lần (' || coalesce(nullif(new.error, ''), '?')
                          || ') — admin đã được báo, sẽ tạo lại hoặc hoàn tiền cho bạn.', 400);
      end if;
    end if;
  end if;
  return new;
end $function$;
drop trigger if exists cp_switch_before on public.cloud_phones;
create trigger cp_switch_before before update on public.cloud_phones for each row execute function public._cp_switch_before();

-- ---------- 11) ADMIN: 🧹 DỌN MÁY ĐỔI ANDROID ----------
-- số máy + danh sách máy mới đang KẸT / LỖI (khách đang không có máy) để admin bấm 🔁 Tạo lại
create or replace function public.admin_switch_info() returns json
language plpgsql stable security definer set search_path = public as $$
begin
  if not is_admin() then raise exception 'NOT_ADMIN'; end if;
  return json_build_object(
    'old_live', (select count(*) from cloud_phones o where o.switch_to is not null and o.status in ('active', 'expired')
                   and exists (select 1 from cloud_phones x where x.id = o.switch_to and x.replaces = o.id and x.status in ('pending', 'creating', 'active'))),
    'old_deleting', (select count(*) from cloud_phones o where o.switch_to is not null and o.status = 'cancelling'),
    'waiting', (select count(*) from cloud_phones x where x.replaces is not null and x.status = 'pending' and x.node = 'wait-old'),
    'rows', (select coalesce(json_agg(r order by r.created_at), '[]'::json) from (
        select x.id, x.name, x.android, x.status, x.node, x.error, x.sw_try, x.created_at, x.updated_at, x.user_id, pf.username,
               o.status as old_status, o.node as old_node,
               case when x.status = 'error' then 'failed' when x.node = 'wait-old' then 'waiting' else 'stuck' end as kind
          from cloud_phones x
          left join cloud_phones o on o.id = x.replaces
          left join profiles pf on pf.id = x.user_id
         where x.replaces is not null and (
               (x.status = 'error' and coalesce(o.status, 'cancelled') in ('cancelled', 'cancelling'))
            or (x.status = 'pending' and x.node = 'wait-old' and greatest(x.created_at, x.updated_at) < now() - interval '5 minutes')
            or (x.status in ('pending', 'creating') and coalesce(x.node, '') <> 'wait-old'
                and greatest(x.created_at, x.updated_at) < now() - interval '15 minutes'))
         order by x.created_at limit 100) r));
end $$;

-- 🧹 XOÁ SẠCH: · máy cũ còn chạy song song máy mới (đổi kiểu cũ) → máy chủ xoá máy ảo + dữ liệu, web ẩn
--              · máy cũ xoá mãi chưa xong (máy chủ tắt / lỗi quá 10 phút) → web ghi đã xoá (ẩn), máy chủ xoá máy ảo khi bật lại
--                hoặc khi admin bấm dọn máy chủ (phonectl dondep) · máy mới đang chờ mà máy cũ đã xoá → tạo ngay
create or replace function public.admin_switch_cleanup() returns json
language plpgsql security definer set search_path = public as $$
declare n_old int := 0; n_forced int := 0; n_rel int := 0; rw record;
begin
  if not is_admin() then raise exception 'NOT_ADMIN'; end if;
  for rw in select c.id, c.switch_to, x.android
             from cloud_phones c join cloud_phones x on x.id = c.switch_to and x.replaces = c.id
            where c.status in ('active', 'expired') and x.status in ('pending', 'creating', 'active')
            for update of c loop
    update cloud_phone_shares set phone_id = rw.switch_to where phone_id = rw.id;
    update cloud_phones set status = 'cancelling', updated_at = now(),
           error = 'Đã đổi sang Android ' || coalesce(rw.android, '?') || ' — máy cũ và dữ liệu cũ đã bị xoá.'
     where id = rw.id;
    n_old := n_old + 1;
  end loop;
  with f as (
    update cloud_phones c set status = 'cancelled', updated_at = now(),
           error = left(coalesce(c.error, '') || ' (admin dọn: web ghi đã xoá)', 400)
     where c.switch_to is not null and c.status = 'cancelling'
       and (c.node is null or c.node = 'wait-old'
            or c.updated_at < now() - interval '10 minutes'
            or not exists (select 1 from cloud_nodes nd where nd.id = c.node and nd.updated_at > now() - interval '3 minutes'))
    returning 1)
  select count(*) into n_forced from f;
  with r as (
    update cloud_phones x set node = null, created_at = now(), updated_at = now()
     where x.replaces is not null and x.status = 'pending' and x.node = 'wait-old'
       and not exists (select 1 from cloud_phones o where o.id = x.replaces and o.status <> 'cancelled')
    returning 1)
  select count(*) into n_rel from r;
  return json_build_object('old', n_old, 'forced', n_forced, 'released', n_rel);
end $$;

-- 🔁 TẠO LẠI máy mới đổi Android bị lỗi / kẹt: về hàng chờ, máy chủ còn chỗ nhận lại (máy ảo đã có trên 1 máy chủ → máy chủ đó làm tiếp)
create or replace function public.admin_switch_retry(p_id uuid) returns json
language plpgsql security definer set search_path = public as $$
declare x cloud_phones;
begin
  if not is_admin() then raise exception 'NOT_ADMIN'; end if;
  select * into x from cloud_phones where id = p_id for update;
  if not found or x.replaces is null then raise exception 'NO_PHONE'; end if;
  if x.status not in ('error', 'pending', 'creating') then raise exception 'SWITCH_NOT_STUCK: Máy này không bị kẹt / lỗi'; end if;
  update cloud_phones
     set status = 'pending', sw_try = 0, error = null, created_at = now(), updated_at = now(),
         node = case when container is null or node = 'wait-old' then null else node end,
         port = case when container is null then null else port end,
         stream_url = case when container is null then null else stream_url end
   where id = x.id;
  return json_build_object('ok', true, 'id', x.id);
end $$;

revoke execute on function public._cp_switch_before(), public._cp_after_update() from public, anon, authenticated;
revoke execute on function public.cloudphone_switch_android(uuid, text) from public, anon;
grant execute on function public.cloudphone_switch_android(uuid, text) to authenticated, service_role;
revoke execute on function public.admin_switch_info(), public.admin_switch_cleanup(), public.admin_switch_retry(uuid) from public, anon;
grant execute on function public.admin_switch_info(), public.admin_switch_cleanup(), public.admin_switch_retry(uuid) to authenticated, service_role;

-- ---------- 9) QUYỀN: hàm nội bộ không gọi thẳng được từ app / web ----------
revoke execute on function public._blue_cfg() from public, anon, authenticated;
revoke execute on function public._blue_add(uuid, bigint, text, text, text) from public, anon, authenticated;
revoke execute on function public._blue_can_use(uuid) from public, anon, authenticated;
revoke execute on function public._blue_take(uuid, bigint) from public, anon, authenticated;
revoke execute on function public._blue_ref_bonus(uuid) from public, anon, authenticated;
revoke execute on function public._blue_cashback(uuid, bigint, text, text) from public, anon, authenticated;
revoke execute on function public._blue_on_sale() from public, anon, authenticated;
revoke execute on function public._blue_on_order() from public, anon, authenticated;
revoke execute on function public._blue_on_topup() from public, anon, authenticated;
revoke execute on function public._blue_has_phone(uuid), public._blue_invited_today(uuid) from public, anon, authenticated;
-- hàm của khách: phải đăng nhập (giống v23) · hàm admin: tự kiểm admin + khoá người chưa đăng nhập (giống khoa-ham-admin)
revoke execute on function public.blue_info(), public.blue_checkin(), public.blue_task(text),
  public.cloudphone_order_custom(integer, integer, integer, text, text, integer, integer, text, boolean, text, boolean),
  public.cloudphone_renew(uuid, integer, text, boolean),
  public.admin_blue_set(jsonb), public.admin_blue_add(text, bigint, text), public.admin_blue_stats()
  from public, anon;
grant execute on function public.blue_info(), public.blue_checkin(), public.blue_task(text),
  public.cloudphone_order_custom(integer, integer, integer, text, text, integer, integer, text, boolean, text, boolean),
  public.cloudphone_renew(uuid, integer, text, boolean),
  public.admin_blue_set(jsonb), public.admin_blue_add(text, bigint, text), public.admin_blue_stats()
  to authenticated, service_role;
-- hoàn tiền máy tạo lỗi: CHỈ máy chủ (service_role) gọi được
revoke execute on function public.cloudphone_refund(uuid, text) from public, anon, authenticated;
grant execute on function public.cloudphone_refund(uuid, text) to service_role;

notify pgrst, 'reload schema';
commit;

select 'v28 xong' as ket_qua,
       (select count(*) from information_schema.columns where table_schema = 'public' and table_name = 'profiles' and column_name = 'blue') as cot_blue,
       (select count(*) from pg_trigger where tgname in ('blue_on_sale', 'blue_on_order', 'blue_on_topup')) as trigger_blue,
       (select pronargs from pg_proc where proname = 'cloudphone_order_custom' and pronamespace = 'public'::regnamespace order by pronargs desc limit 1) as thue_may_so_tham_so,
       (select count(*) from pg_proc where proname in ('blue_info', 'blue_checkin', 'blue_task', 'admin_blue_set', 'admin_blue_add', 'admin_blue_stats') and pronamespace = 'public'::regnamespace) as ham_blue,
       (select count(*) from pg_proc where proname in ('admin_switch_info', 'admin_switch_cleanup', 'admin_switch_retry') and pronamespace = 'public'::regnamespace) as ham_don_android,
       (select count(*) from information_schema.columns where table_schema = 'public' and table_name = 'cloud_phones' and column_name = 'sw_try') as cot_tao_lai;
