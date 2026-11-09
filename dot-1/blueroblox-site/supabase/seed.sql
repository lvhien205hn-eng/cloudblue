-- Sản phẩm mẫu (chạy sau schema.sql nếu muốn có sẵn danh sách để sửa).
-- Kho đang trống: vào trang admin › Sản phẩm › "Nhập kho" để thêm hàng thật.
insert into public.products (cat, name, price, features, hot, sort, plans) values
 ('clone','Clone Roblox trắng – mới tạo',500,'{"Đổi pass được","Giao tự động"}',true,1,'[]'),
 ('clone','Clone Roblox đã xác minh email',1000,'{"Có email","Đổi pass được"}',true,2,'[]'),
 ('clone','Clone aged 30 ngày',1800,'{"30+ ngày","Full info"}',false,3,'[]'),
 ('clone','Clone aged 60 ngày + backup security',2500,'{"60+ ngày","Có backup"}',false,4,'[]'),
 ('clone','Clone aged 1 năm',6000,'{"365+ ngày","Full info"}',false,5,'[]'),
 ('vps','VPS GPU RTX 3060 12GB',30000,'{"8 vCPU","16GB RAM","Windows"}',true,7,'[{"days":1,"price":30000},{"days":7,"price":180000},{"days":15,"price":330000},{"days":30,"price":600000}]'),
 ('vps','VPS GPU RTX 4070 12GB',45000,'{"12 vCPU","32GB RAM","Treo nhiều tab"}',true,8,'[{"days":7,"price":280000},{"days":15,"price":520000},{"days":30,"price":950000}]'),
 ('vps','VPS GPU RTX 4090 24GB',90000,'{"16 vCPU","64GB RAM","1Gbps"}',false,9,'[{"days":7,"price":590000},{"days":15,"price":1090000},{"days":30,"price":1990000}]');
