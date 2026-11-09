-- ===== Chống spam/DDoS tầng ứng dụng: đếm số lần gọi theo IP trong một khoảng thời gian =====
-- Chạy file này 1 lần trong Supabase → SQL Editor → Run.

create table if not exists public.rate_limits (
  key text primary key,
  count int not null default 0,
  reset_at timestamptz not null default now()
);
alter table public.rate_limits enable row level security;
-- Không tạo policy nào → chỉ service role (các API) đụng được, khách không đọc/ghi trực tiếp.

-- rl_hit: cộng 1 vào bộ đếm của key; trả về TRUE nếu còn trong hạn mức, FALSE nếu vượt.
create or replace function public.rl_hit(p_key text, p_limit int, p_window int)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare c int; now_ts timestamptz := now();
begin
  insert into rate_limits(key, count, reset_at)
    values (p_key, 1, now_ts + make_interval(secs => p_window))
  on conflict (key) do update set
    count    = case when rate_limits.reset_at < now_ts then 1 else rate_limits.count + 1 end,
    reset_at = case when rate_limits.reset_at < now_ts then now_ts + make_interval(secs => p_window) else rate_limits.reset_at end
  returning count into c;
  return c <= p_limit;
end $$;

-- Dọn dòng hết hạn (gọi thỉnh thoảng, không bắt buộc)
create or replace function public.rl_gc() returns void
language sql security definer set search_path = public as $$
  delete from rate_limits where reset_at < now() - interval '1 hour';
$$;
