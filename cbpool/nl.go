package main

// Netlink tối thiểu (chỉ thư viện chuẩn): gắn / gỡ địa chỉ IPv6 /128 cho từng proxy, bật card mạng (bộ thử).
// Không cần lệnh "ip" → chạy được cả trong bộ thử không có iproute2.

import (
	"encoding/binary"
	"fmt"
	"net"
	"sync/atomic"
	"syscall"
	"unsafe"
)

const (
	ifaFlags       = 8     // IFA_FLAGS (u32, cờ mở rộng)
	ifaFNoPrefixRt = 0x200 // IFA_F_NOPREFIXROUTE
)

var nlSeq uint32

func ne() binary.ByteOrder { // thứ tự byte của máy (netlink dùng thứ tự máy)
	x := uint16(1)
	if *(*byte)(unsafe.Pointer(&x)) == 1 {
		return binary.LittleEndian
	}
	return binary.BigEndian
}

func rta(typ uint16, data []byte) []byte {
	l := syscall.SizeofRtAttr + len(data)
	b := make([]byte, (l+3)&^3)
	ne().PutUint16(b[0:], uint16(l))
	ne().PutUint16(b[2:], typ)
	copy(b[syscall.SizeofRtAttr:], data)
	return b
}

func nlMsg(typ, flags uint16, body []byte, attrs ...[]byte) []byte {
	n := syscall.NLMSG_HDRLEN + len(body)
	for _, a := range attrs {
		n += len(a)
	}
	b := make([]byte, 0, n)
	h := make([]byte, syscall.NLMSG_HDRLEN)
	ne().PutUint32(h[0:], uint32(n))
	ne().PutUint16(h[4:], typ)
	ne().PutUint16(h[6:], flags|syscall.NLM_F_REQUEST|syscall.NLM_F_ACK)
	ne().PutUint32(h[8:], atomic.AddUint32(&nlSeq, 1))
	b = append(b, h...)
	b = append(b, body...)
	for _, a := range attrs {
		b = append(b, a...)
	}
	return b
}

// nlDo gửi 1 yêu cầu netlink route và chờ ACK (lỗi của nhân trả về dạng syscall.Errno).
func nlDo(msg []byte) error {
	fd, err := syscall.Socket(syscall.AF_NETLINK, syscall.SOCK_RAW|syscall.SOCK_CLOEXEC, syscall.NETLINK_ROUTE)
	if err != nil {
		return err
	}
	defer syscall.Close(fd)
	tv := syscall.Timeval{Sec: 3}
	syscall.SetsockoptTimeval(fd, syscall.SOL_SOCKET, syscall.SO_RCVTIMEO, &tv)
	if err := syscall.Bind(fd, &syscall.SockaddrNetlink{Family: syscall.AF_NETLINK}); err != nil {
		return err
	}
	if err := syscall.Sendto(fd, msg, 0, &syscall.SockaddrNetlink{Family: syscall.AF_NETLINK}); err != nil {
		return err
	}
	seq := ne().Uint32(msg[8:])
	buf := make([]byte, 65536)
	for {
		n, _, err := syscall.Recvfrom(fd, buf, 0)
		if err != nil {
			return err
		}
		msgs, err := syscall.ParseNetlinkMessage(buf[:n])
		if err != nil {
			return err
		}
		for _, m := range msgs {
			if m.Header.Seq != seq {
				continue
			}
			if m.Header.Type == syscall.NLMSG_ERROR {
				if len(m.Data) < 4 {
					return fmt.Errorf("netlink: trả lời lỗi ngắn")
				}
				if e := int32(ne().Uint32(m.Data[0:4])); e != 0 {
					return syscall.Errno(-e)
				}
				return nil
			}
		}
	}
}

func ifaddrmsg(fam, plen, flags uint8, idx int) []byte {
	b := make([]byte, syscall.SizeofIfAddrmsg)
	b[0], b[1], b[2], b[3] = fam, plen, flags, 0
	ne().PutUint32(b[4:], uint32(idx))
	return b
}

// addr6Add gắn ip/128 vào card idx: không dò trùng (DAD), "hết hạn ưu tiên" (preferred 0) → nhân KHÔNG tự chọn địa chỉ này cho
// kết nối thường của máy chủ; chỉ proxy gắn (bind) đúng địa chỉ mới dùng. Có rồi thì thay (không lỗi).
func addr6Add(idx int, ip net.IP) error {
	ip = ip.To16()
	ci := make([]byte, 16) // ifa_cacheinfo: prefered, valid, cstamp, tstamp
	ne().PutUint32(ci[0:], 0)
	ne().PutUint32(ci[4:], 0xffffffff)
	fl := make([]byte, 4)
	ne().PutUint32(fl, syscall.IFA_F_NODAD|ifaFNoPrefixRt)
	m := nlMsg(syscall.RTM_NEWADDR, syscall.NLM_F_CREATE|syscall.NLM_F_REPLACE,
		ifaddrmsg(syscall.AF_INET6, 128, syscall.IFA_F_NODAD, idx),
		rta(syscall.IFA_LOCAL, ip), rta(syscall.IFA_ADDRESS, ip), rta(syscall.IFA_CACHEINFO, ci), rta(ifaFlags, fl))
	return nlDo(m)
}

// addr6AddPlain gắn địa chỉ thường (bộ thử: giả lập địa chỉ SLAAC /64 của máy chủ).
func addr6AddPlain(idx int, ip net.IP, plen int) error {
	ip = ip.To16()
	m := nlMsg(syscall.RTM_NEWADDR, syscall.NLM_F_CREATE|syscall.NLM_F_REPLACE,
		ifaddrmsg(syscall.AF_INET6, uint8(plen), syscall.IFA_F_NODAD, idx), rta(syscall.IFA_LOCAL, ip), rta(syscall.IFA_ADDRESS, ip))
	return nlDo(m)
}

func addr6Del(idx int, ip net.IP) error {
	ip = ip.To16()
	m := nlMsg(syscall.RTM_DELADDR, 0, ifaddrmsg(syscall.AF_INET6, 128, 0, idx), rta(syscall.IFA_LOCAL, ip), rta(syscall.IFA_ADDRESS, ip))
	err := nlDo(m)
	if err == syscall.EADDRNOTAVAIL || err == syscall.ENODEV {
		return nil
	}
	return err
}

// linkUp bật card (bộ thử trong không gian mạng riêng: lo mặc định tắt).
func linkUp(idx int) error {
	b := make([]byte, syscall.SizeofIfInfomsg)
	b[0] = syscall.AF_UNSPEC
	ne().PutUint32(b[4:], uint32(idx))
	ne().PutUint32(b[8:], syscall.IFF_UP)
	ne().PutUint32(b[12:], syscall.IFF_UP)
	return nlDo(nlMsg(syscall.RTM_NEWLINK, 0, b))
}
