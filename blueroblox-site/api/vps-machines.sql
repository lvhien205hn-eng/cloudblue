-- ============ QUẢN LÝ MÁY VPS CHO KHÁCH (gán tên máy, hạn dùng, gia hạn, huỷ) ============
-- Chạy 1 lần trong Supabase → SQL Editor → Run.

create table if not exists public.vps_machines (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references public.profiles on delete cascade,
  order_id     uuid references public.orders on delete set null,
  product_id   uuid references public.products on delete set null,
  product_name text not null,
  machine_name text not null,
  plan_days    int,
  renew_price  bigint,               -- giá 1 kỳ gia hạn (VND)
  expires_at   timestamptz not null,
  status       text not null default 'active',   -- active | cancelled
  notified_warn boolean not null default false,    -- đã báo "sắp hết hạn"
  notified_exp  boolean not null default false,    -- đã báo "đã hết hạn"
  created_at   timestamptz not null default now()
);
alter table public.vps_machines add column if not exists notified_warn boolean not null default false;
alter table public.vps_machines add column if not exists notified_exp  boolean not null default false;
create index if not exists vps_machines_user on public.vps_machines(user_id);
alter table public.vps_machines enable row level security;
drop policy if exists "own or admin read" on public.vps_machines;
create policy "own or admin read" on public.vps_machines for select using (user_id = auth.uid() or public.is_admin());

-- Giá 1 kỳ theo số ngày của sản phẩm (ưu tiên gói đúng số ngày, không có thì giá gốc)
create or replace function public._vps_price(p products, p_days int) returns bigint
language plpgsql as $$
declare v bigint;
begin
  if p_days is not null and jsonb_array_length(p.plans) > 0 then
    select (x->>'price')::bigint into v from jsonb_array_elements(p.plans) x where (x->>'days')::int = p_days limit 1;
  end if;
  return coalesce(v, p.price);
end $$;

-- ADMIN: giao đơn VPS = gán tên máy cho khách (mỗi dòng 1 máy). Hạn = ngày giao + số ngày gói.
create or replace function public.admin_assign_vps(p_order uuid, p_names text) returns int
language plpgsql security definer set search_path = public as $$
declare o orders; p products; v_days int; v_price bigint; v_exp timestamptz;
        v_names text[]; nm text; n int := 0; v_items text := '';
begin
  if not is_admin() then raise exception 'NOT_ADMIN'; end if;
  select * into o from orders where id = p_order and status = 'pending' for update;
  if not found then return 0; end if;
  select * into p from products where id = o.product_id;
  v_days  := coalesce(o.days, 30);
  v_price := coalesce(_vps_price(p, o.days), o.total / greatest(o.qty,1));
  v_exp   := now() + make_interval(days => v_days);

  v_names := string_to_array(replace(p_names, E'\r', ''), E'\n');
  foreach nm in array v_names loop
    if trim(nm) <> '' then
      insert into vps_machines(user_id, order_id, product_id, product_name, machine_name, plan_days, renew_price, expires_at)
      values (o.user_id, o.id, o.product_id, o.product_name, trim(nm), v_days, v_price, v_exp);
      n := n + 1;
      v_items := v_items || '🖥 ' || trim(nm) || ' | Hết hạn: ' || to_char(v_exp at time zone 'Asia/Ho_Chi_Minh', 'DD/MM/YYYY HH24:MI') || E'\n';
    end if;
  end loop;
  if n = 0 then raise exception 'EMPTY'; end if;

  update orders set items = trim(v_items), status = 'done', delivered_at = now() where id = o.id;
  return n;
end $$;

-- KHÁCH: gia hạn 1 máy theo gói ngày. Trừ số dư, cộng thêm ngày, tạo đơn ghi nhận.
create or replace function public.renew_vps(p_machine uuid, p_days int) returns vps_machines
language plpgsql security definer set search_path = public as $$
declare me profiles; m vps_machines; p products; v_price bigint; v_base timestamptz; v_exp timestamptz; o orders;
begin
  select * into me from profiles where id = auth.uid() for update;
  if not found then raise exception 'NOT_LOGGED_IN'; end if;
  if me.locked then raise exception 'LOCKED'; end if;
  select * into m from vps_machines where id = p_machine and user_id = me.id for update;
  if not found then raise exception 'NO_MACHINE'; end if;
  if p_days is null or p_days < 1 then raise exception 'BAD_PLAN'; end if;

  select * into p from products where id = m.product_id;
  if found then v_price := _vps_price(p, p_days);
  else v_price := m.renew_price; if p_days <> coalesce(m.plan_days, p_days) then raise exception 'BAD_PLAN'; end if; end if;
  if v_price is null then raise exception 'BAD_PLAN'; end if;
  if me.balance < v_price then raise exception 'INSUFFICIENT_BALANCE'; end if;

  v_base := greatest(now(), m.expires_at);           -- gia hạn sớm thì cộng dồn từ hạn cũ
  v_exp  := v_base + make_interval(days => p_days);

  update profiles set balance = balance - v_price where id = me.id;
  update vps_machines set expires_at = v_exp, plan_days = p_days, renew_price = v_price, status = 'active',
    notified_warn = false, notified_exp = false where id = m.id returning * into m;

  insert into orders(user_id, product_id, product_name, qty, total, items, status, days, delivered_at)
  values (me.id, m.product_id, m.product_name || ' · gia hạn ' || p_days || ' ngày', 1, v_price,
          '🖥 ' || m.machine_name || ' | Gia hạn +' || p_days || ' ngày → ' || to_char(v_exp at time zone 'Asia/Ho_Chi_Minh', 'DD/MM/YYYY HH24:MI'),
          'done', p_days, now()) returning * into o;
  return m;
end $$;

-- KHÁCH: huỷ bỏ (không gia hạn nữa) — ẩn máy khỏi danh sách đang dùng.
create or replace function public.cancel_vps(p_machine uuid) returns void
language plpgsql security definer set search_path = public as $$
begin
  update vps_machines set status = 'cancelled' where id = p_machine and user_id = auth.uid();
end $$;

revoke execute on function public._vps_price(products, int) from public, anon, authenticated;

-- ============ ADMIN: toàn quyền quản lý máy VPS của khách ============
-- Cộng/bớt ngày cho máy (admin tặng thêm, hoặc chỉnh). p_days có thể âm.
create or replace function public.admin_vps_extend(p_machine uuid, p_days int) returns vps_machines
language plpgsql security definer set search_path = public as $$
declare m vps_machines; v_base timestamptz;
begin
  if not is_admin() then raise exception 'NOT_ADMIN'; end if;
  select * into m from vps_machines where id = p_machine for update;
  if not found then raise exception 'NO_MACHINE'; end if;
  v_base := greatest(now(), m.expires_at);
  update vps_machines set expires_at = v_base + make_interval(days => p_days), status = 'active',
    notified_warn = false, notified_exp = false where id = m.id returning * into m;
  return m;
end $$;

-- Sửa tên máy và/hoặc đặt hạn chính xác (p_name/p_expires để trống thì giữ nguyên).
create or replace function public.admin_vps_set(p_machine uuid, p_name text default null, p_expires timestamptz default null) returns vps_machines
language plpgsql security definer set search_path = public as $$
declare m vps_machines;
begin
  if not is_admin() then raise exception 'NOT_ADMIN'; end if;
  update vps_machines set
    machine_name = coalesce(nullif(trim(coalesce(p_name,'')), ''), machine_name),
    expires_at   = coalesce(p_expires, expires_at),
    notified_warn = case when p_expires is not null then false else notified_warn end,
    notified_exp  = case when p_expires is not null then false else notified_exp end
  where id = p_machine returning * into m;
  if not found then raise exception 'NO_MACHINE'; end if;
  return m;
end $$;

-- Xoá hẳn 1 máy khỏi hệ thống.
create or replace function public.admin_vps_delete(p_machine uuid) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not is_admin() then raise exception 'NOT_ADMIN'; end if;
  delete from vps_machines where id = p_machine;
end $$;

-- Thêm máy thủ công cho 1 khách (không cần qua đơn hàng) — tiện khi admin tự tạo máy.
create or replace function public.admin_vps_create(p_user uuid, p_name text, p_days int, p_product_name text default 'VPS') returns vps_machines
language plpgsql security definer set search_path = public as $$
declare m vps_machines;
begin
  if not is_admin() then raise exception 'NOT_ADMIN'; end if;
  if coalesce(trim(p_name),'') = '' then raise exception 'EMPTY'; end if;
  insert into vps_machines(user_id, product_name, machine_name, plan_days, expires_at)
  values (p_user, p_product_name, trim(p_name), p_days, now() + make_interval(days => coalesce(p_days,30)))
  returning * into m;
  return m;
end $$;
