-- =====================================================================
-- BLUEROBLOX – cơ sở dữ liệu
-- Chạy toàn bộ file này 1 lần trong Supabase › SQL Editor › New query › Run
-- =====================================================================

create extension if not exists pgcrypto;

-- ---------- KHÁCH HÀNG ----------
create table if not exists public.profiles (
  id          uuid primary key references auth.users on delete cascade,
  username    text unique not null check (username ~ '^[A-Za-z0-9_]{3,24}$'),
  email       text not null,
  balance     bigint not null default 0 check (balance >= 0),
  role        text not null default 'user' check (role in ('user','admin')),
  locked      boolean not null default false,
  created_at  timestamptz not null default now()
);

create or replace function public.is_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select exists(select 1 from profiles where id = auth.uid() and role = 'admin' and not locked);
$$;

-- Tự tạo hồ sơ khách khi có người đăng ký
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into profiles(id, username, email)
  values (new.id,
          coalesce(nullif(new.raw_user_meta_data->>'username',''), 'user_' || substr(replace(new.id::text,'-',''),1,8)),
          new.email);
  return new;
end $$;
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

create or replace function public.username_available(p_username text) returns boolean
language sql stable security definer set search_path = public as $$
  select not exists(select 1 from profiles where lower(username) = lower(p_username));
$$;

-- ---------- SẢN PHẨM & KHO ----------
create table if not exists public.products (
  id        uuid primary key default gen_random_uuid(),
  cat       text not null check (cat in ('clone','vps')),
  name      text not null,
  price     bigint not null check (price >= 0),        -- VND
  features  text[] not null default '{}',
  hot       boolean not null default false,
  sort      int not null default 100,
  plans     jsonb not null default '[]',  -- gói ngày cho VPS: [{"days":7,"price":150000}, ...]
  created_at timestamptz not null default now()
);
alter table public.products add column if not exists plans jsonb not null default '[]';

-- Mỗi dòng kho = 1 tài khoản / 1 VPS sẽ giao cho khách
create table if not exists public.stock (
  id          bigserial primary key,
  product_id  uuid not null references products on delete cascade,
  data        text not null,
  order_id    uuid,
  created_at  timestamptz not null default now()
);
create index if not exists stock_free on public.stock(product_id) where order_id is null;

-- Danh sách hiển thị cho khách: chỉ lộ số lượng còn, không lộ dữ liệu kho
drop view if exists public.product_list;
create view public.product_list as
  select p.id, p.cat, p.name, p.price, p.features, p.hot, p.sort, p.plans,
         (select count(*) from stock s where s.product_id = p.id and s.order_id is null)::int as stock
  from products p;

-- ---------- CÀI ĐẶT TRANG ----------
create table if not exists public.settings (
  id    int primary key default 1 check (id = 1),
  data  jsonb not null default '{}'
);
insert into public.settings(id, data) values (1, '{}') on conflict do nothing;

-- ---------- NẠP TIỀN & ĐƠN HÀNG ----------
create table if not exists public.topups (
  id         bigserial primary key,
  user_id    uuid not null references profiles on delete cascade,
  memo       text unique not null,
  amount     bigint not null check (amount > 0),
  status     text not null default 'pending' check (status in ('pending','done')),
  bank_ref   text unique,
  created_at timestamptz not null default now(),
  done_at    timestamptz
);

create table if not exists public.orders (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references profiles on delete cascade,
  product_id   uuid references products on delete set null,
  product_name text not null,
  qty          int not null,
  total        bigint not null,
  items        text not null,
  created_at   timestamptz not null default now()
);

-- ---------- QUYỀN TRUY CẬP (Row Level Security) ----------
alter table public.profiles enable row level security;
alter table public.products enable row level security;
alter table public.stock    enable row level security;
alter table public.settings enable row level security;
alter table public.topups   enable row level security;
alter table public.orders   enable row level security;

drop policy if exists "own or admin read" on public.profiles;
create policy "own or admin read" on public.profiles for select using (id = auth.uid() or is_admin());

drop policy if exists "anyone read" on public.products;
create policy "anyone read" on public.products for select using (true);
drop policy if exists "admin write" on public.products;
create policy "admin write" on public.products for all using (is_admin()) with check (is_admin());

drop policy if exists "admin only" on public.stock;
create policy "admin only" on public.stock for all using (is_admin()) with check (is_admin());

drop policy if exists "anyone read" on public.settings;
create policy "anyone read" on public.settings for select using (true);
drop policy if exists "admin write" on public.settings;
create policy "admin write" on public.settings for update using (is_admin()) with check (is_admin());

drop policy if exists "own or admin read" on public.topups;
create policy "own or admin read" on public.topups for select using (user_id = auth.uid() or is_admin());

drop policy if exists "own or admin read" on public.orders;
create policy "own or admin read" on public.orders for select using (user_id = auth.uid() or is_admin());

grant select on public.product_list to anon, authenticated;

-- ---------- HÀM CHO KHÁCH ----------
-- Tạo lệnh nạp, trả về nội dung chuyển khoản riêng
create or replace function public.create_topup(p_amount bigint) returns public.topups
language plpgsql security definer set search_path = public as $$
declare
  me profiles; s jsonb; v_min bigint; v_prefix text; t topups;
begin
  select * into me from profiles where id = auth.uid();
  if not found then raise exception 'NOT_LOGGED_IN'; end if;
  if me.locked then raise exception 'LOCKED'; end if;
  select data into s from settings where id = 1;
  v_min := coalesce((s->>'minTop')::bigint, 10000);
  v_prefix := upper(regexp_replace(coalesce(s->>'prefix','BR'), '[^A-Za-z0-9]', '', 'g'));
  if v_prefix = '' then v_prefix := 'BR'; end if;
  if p_amount < v_min then raise exception 'MIN_AMOUNT'; end if;
  if (select count(*) from topups where user_id = me.id and status = 'pending' and created_at > now() - interval '1 hour') >= 5
    then raise exception 'TOO_MANY'; end if;
  insert into topups(user_id, memo, amount)
  values (me.id, v_prefix || upper(substr(encode(gen_random_bytes(6),'hex'),1,8)), p_amount)
  returning * into t;
  return t;
end $$;

-- Mua hàng: trừ tiền + lấy hàng trong kho, tất cả trong 1 giao dịch
-- p_days: số ngày thuê khi sản phẩm có gói ngày (VPS); để trống với Clone
drop function if exists public.buy_product(uuid, int);
create or replace function public.buy_product(p_product uuid, p_qty int, p_days int default null) returns public.orders
language plpgsql security definer set search_path = public as $$
declare
  me profiles; p products; v_price bigint; v_name text; v_suffix text := ''; v_total bigint; v_ids bigint[]; v_items text; o orders;
begin
  if p_qty < 1 or p_qty > 500 then raise exception 'BAD_QTY'; end if;
  select * into me from profiles where id = auth.uid() for update;
  if not found then raise exception 'NOT_LOGGED_IN'; end if;
  if me.locked then raise exception 'LOCKED'; end if;
  select * into p from products where id = p_product;
  if not found then raise exception 'NO_PRODUCT'; end if;
  v_price := p.price; v_name := p.name;
  if jsonb_array_length(p.plans) > 0 then
    select (x->>'price')::bigint into v_price from jsonb_array_elements(p.plans) x where (x->>'days')::int = p_days limit 1;
    if v_price is null then raise exception 'BAD_PLAN'; end if;
    v_name := p.name || ' · ' || p_days || ' ngày';
    v_suffix := ' | Hết hạn: ' || to_char((now() at time zone 'Asia/Ho_Chi_Minh') + make_interval(days => p_days), 'DD/MM/YYYY HH24:MI');
  end if;
  v_total := v_price * p_qty;
  if me.balance < v_total then raise exception 'INSUFFICIENT_BALANCE'; end if;

  select array_agg(id) into v_ids from (
    select id from stock where product_id = p.id and order_id is null
    order by id limit p_qty for update skip locked) x;
  if coalesce(array_length(v_ids,1),0) < p_qty then raise exception 'OUT_OF_STOCK'; end if;

  select string_agg(data || v_suffix, E'\n' order by id) into v_items from stock where id = any(v_ids);
  insert into orders(user_id, product_id, product_name, qty, total, items)
  values (me.id, p.id, v_name, p_qty, v_total, v_items) returning * into o;
  update stock set order_id = o.id where id = any(v_ids);
  update profiles set balance = balance - v_total where id = me.id;
  return o;
end $$;

-- ---------- HÀM CHO WEBHOOK NGÂN HÀNG (chỉ máy chủ gọi được) ----------
create or replace function public.credit_topup(p_memo text, p_amount bigint, p_ref text) returns boolean
language plpgsql security definer set search_path = public as $$
declare t topups;
begin
  if exists(select 1 from topups where bank_ref = p_ref) then return false; end if;
  select * into t from topups where memo = p_memo and status = 'pending' for update;
  if not found or p_amount < t.amount then return false; end if;
  update topups set status = 'done', done_at = now(), bank_ref = p_ref, amount = p_amount where id = t.id;
  update profiles set balance = balance + p_amount where id = t.user_id;
  return true;
end $$;
revoke execute on function public.credit_topup(text,bigint,text) from public, anon, authenticated;

-- ---------- HÀM CHO ADMIN ----------
create or replace function public.admin_adjust_balance(p_user uuid, p_delta bigint) returns bigint
language plpgsql security definer set search_path = public as $$
declare v bigint;
begin
  if not is_admin() then raise exception 'NOT_ADMIN'; end if;
  update profiles set balance = greatest(0, balance + p_delta) where id = p_user returning balance into v;
  return v;
end $$;

create or replace function public.admin_set_locked(p_user uuid, p_locked boolean) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not is_admin() then raise exception 'NOT_ADMIN'; end if;
  if p_user = auth.uid() then raise exception 'SELF'; end if;
  update profiles set locked = p_locked where id = p_user;
end $$;

create or replace function public.admin_approve_topup(p_id bigint) returns boolean
language plpgsql security definer set search_path = public as $$
declare t topups;
begin
  if not is_admin() then raise exception 'NOT_ADMIN'; end if;
  select * into t from topups where id = p_id and status = 'pending' for update;
  if not found then return false; end if;
  update topups set status = 'done', done_at = now(), bank_ref = 'MANUAL-' || p_id where id = t.id;
  update profiles set balance = balance + t.amount where id = t.user_id;
  return true;
end $$;

-- Nhập kho: mỗi dòng là 1 sản phẩm giao cho khách
create or replace function public.admin_add_stock(p_product uuid, p_lines text) returns int
language plpgsql security definer set search_path = public as $$
declare n int;
begin
  if not is_admin() then raise exception 'NOT_ADMIN'; end if;
  insert into stock(product_id, data)
  select p_product, trim(l) from unnest(string_to_array(replace(p_lines, E'\r', ''), E'\n')) l where trim(l) <> '';
  get diagnostics n = row_count;
  return n;
end $$;

-- Xoá hàng chưa bán của 1 sản phẩm
create or replace function public.admin_clear_stock(p_product uuid) returns int
language plpgsql security definer set search_path = public as $$
declare n int;
begin
  if not is_admin() then raise exception 'NOT_ADMIN'; end if;
  delete from stock where product_id = p_product and order_id is null;
  get diagnostics n = row_count;
  return n;
end $$;

-- =====================================================================
-- SAU KHI BẠN ĐĂNG KÝ TÀI KHOẢN TRÊN WEB, chạy dòng dưới (thay email)
-- để biến tài khoản đó thành ADMIN:
--
--   update public.profiles set role = 'admin' where email = 'email-cua-ban@gmail.com';
-- =====================================================================

-- =====================================================================
-- PHẦN 2 – GIAO THỦ CÔNG (VPS) + THÔNG BÁO TELEGRAM/EMAIL
-- (Nếu bạn đã chạy file này trước đây, chỉ cần chạy lại từ dòng này trở xuống)
-- =====================================================================
alter table public.products add column if not exists manual boolean not null default false;
alter table public.products add column if not exists manual_stock int not null default 0;
alter table public.orders add column if not exists status text not null default 'done';
alter table public.orders add column if not exists days int;
alter table public.orders add column if not exists delivered_at timestamptz;
do $$ begin
  alter table public.products add constraint products_manual_stock_chk check (manual_stock >= 0);
exception when duplicate_object then null; end $$;
do $$ begin
  alter table public.orders add constraint orders_status_chk check (status in ('pending','done','refunded'));
exception when duplicate_object then null; end $$;

drop view if exists public.product_list;
create view public.product_list as
  select p.id, p.cat, p.name, p.price, p.features, p.hot, p.sort, p.plans, p.manual,
         case when p.manual then p.manual_stock
              else (select count(*) from stock s where s.product_id = p.id and s.order_id is null)::int end as stock
  from products p;
grant select on public.product_list to anon, authenticated;

-- Mua hàng (bản đầy đủ): hàng có sẵn trong kho thì giao ngay; hàng "giao thủ công" thì tạo đơn chờ giao
create or replace function public.buy_product(p_product uuid, p_qty int, p_days int default null) returns public.orders
language plpgsql security definer set search_path = public as $$
declare
  me profiles; p products; v_price bigint; v_name text; v_suffix text := ''; v_total bigint; v_ids bigint[]; v_items text; o orders;
begin
  if p_qty < 1 or p_qty > 500 then raise exception 'BAD_QTY'; end if;
  select * into me from profiles where id = auth.uid() for update;
  if not found then raise exception 'NOT_LOGGED_IN'; end if;
  if me.locked then raise exception 'LOCKED'; end if;
  select * into p from products where id = p_product for update;
  if not found then raise exception 'NO_PRODUCT'; end if;

  v_price := p.price; v_name := p.name;
  if jsonb_array_length(p.plans) > 0 then
    select (x->>'price')::bigint into v_price from jsonb_array_elements(p.plans) x where (x->>'days')::int = p_days limit 1;
    if v_price is null then raise exception 'BAD_PLAN'; end if;
    v_name := p.name || ' · ' || p_days || ' ngày';
    v_suffix := ' | Hết hạn: ' || to_char((now() at time zone 'Asia/Ho_Chi_Minh') + make_interval(days => p_days), 'DD/MM/YYYY HH24:MI');
  else
    p_days := null;
  end if;
  v_total := v_price * p_qty;
  if me.balance < v_total then raise exception 'INSUFFICIENT_BALANCE'; end if;

  if p.manual then
    if p.manual_stock < p_qty then raise exception 'OUT_OF_STOCK'; end if;
    update products set manual_stock = manual_stock - p_qty where id = p.id;
    insert into orders(user_id, product_id, product_name, qty, total, items, status, days)
    values (me.id, p.id, v_name, p_qty, v_total, 'Đang chuẩn bị. Admin sẽ giao thông tin trong ít phút.', 'pending', p_days)
    returning * into o;
    update profiles set balance = balance - v_total where id = me.id;
    return o;
  end if;

  select array_agg(id) into v_ids from (
    select id from stock where product_id = p.id and order_id is null
    order by id limit p_qty for update skip locked) x;
  if coalesce(array_length(v_ids,1),0) < p_qty then raise exception 'OUT_OF_STOCK'; end if;
  select string_agg(data || v_suffix, E'\n' order by id) into v_items from stock where id = any(v_ids);
  insert into orders(user_id, product_id, product_name, qty, total, items, status, days, delivered_at)
  values (me.id, p.id, v_name, p_qty, v_total, v_items, 'done', p_days, now()) returning * into o;
  update stock set order_id = o.id where id = any(v_ids);
  update profiles set balance = balance - v_total where id = me.id;
  return o;
end $$;

-- Giao đơn thủ công (dùng chung cho trang admin và bot Telegram)
create or replace function public._deliver(p_order uuid, p_items text) returns boolean
language plpgsql security definer set search_path = public as $$
declare o orders; v_items text;
begin
  if coalesce(trim(p_items), '') = '' then raise exception 'EMPTY'; end if;
  select * into o from orders where id = p_order and status = 'pending' for update;
  if not found then return false; end if;
  v_items := trim(replace(p_items, E'\r', ''));
  if o.days is not null then
    select string_agg(trim(l) || ' | Hết hạn: ' || to_char((now() at time zone 'Asia/Ho_Chi_Minh') + make_interval(days => o.days), 'DD/MM/YYYY HH24:MI'), E'\n')
      into v_items from unnest(string_to_array(v_items, E'\n')) l where trim(l) <> '';
  end if;
  update orders set items = v_items, status = 'done', delivered_at = now() where id = o.id;
  return true;
end $$;

-- Hoàn tiền đơn chưa giao
create or replace function public._refund(p_order uuid) returns boolean
language plpgsql security definer set search_path = public as $$
declare o orders;
begin
  select * into o from orders where id = p_order and status = 'pending' for update;
  if not found then return false; end if;
  update orders set status = 'refunded', items = 'Đơn đã huỷ, tiền đã hoàn vào số dư.' where id = o.id;
  update profiles set balance = balance + o.total where id = o.user_id;
  update products set manual_stock = manual_stock + o.qty where id = o.product_id and manual;
  return true;
end $$;

revoke execute on function public._deliver(uuid, text) from public, anon, authenticated;
revoke execute on function public._refund(uuid) from public, anon, authenticated;
do $$ begin
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    grant execute on function public._deliver(uuid, text) to service_role;
    grant execute on function public._refund(uuid) to service_role;
    grant execute on function public.credit_topup(text, bigint, text) to service_role;
  end if;
end $$;

create or replace function public.admin_deliver_order(p_order uuid, p_items text) returns boolean
language plpgsql security definer set search_path = public as $$
begin
  if not is_admin() then raise exception 'NOT_ADMIN'; end if;
  return _deliver(p_order, p_items);
end $$;

create or replace function public.admin_refund_order(p_order uuid) returns boolean
language plpgsql security definer set search_path = public as $$
begin
  if not is_admin() then raise exception 'NOT_ADMIN'; end if;
  return _refund(p_order);
end $$;
