"""Admin menu management: creation, deletion semantics and image uploads."""

import pytest
from fastapi import HTTPException

from app.models import MenuItem, Order, OrderItem, User, UserRole
from app.routers.admin import _sniff_image


def _png_bytes() -> bytes:
    import struct
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    raw = b"".join(b"\x00" + bytes([200, 120, 60]) * 4 for _ in range(4))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


@pytest.mark.parametrize(
    "data,expected",
    [
        (b"\xff\xd8\xff\xe0rest", ".jpg"),
        (b"\x89PNG\r\n\x1a\nrest", ".png"),
        (b"GIF87a...", ".gif"),
        (b"GIF89a...", ".gif"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", ".webp"),
        (_png_bytes(), ".png"),
    ],
)
def test_sniff_accepts_real_images(data, expected):
    assert _sniff_image(data) == expected


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"<html><body>hi</body></html>",
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        b"%PDF-1.4 fake",
        b"RIFF\x00\x00\x00\x00WAVEfmt ",  # RIFF container, but not WebP
        b"\xff\xd8",  # truncated JPEG magic
    ],
)
def test_sniff_rejects_non_images(data):
    """Content type is decided by magic bytes, never by filename."""
    assert _sniff_image(data) is None


async def test_delete_removes_item_never_ordered(db):
    from app.routers.admin import delete_menu_item

    admin = User(email="a@example.com", role=UserRole.admin)
    item = MenuItem(name_he="מנה חדשה", category="sides", price_agorot=1000)
    db.add_all([admin, item])
    await db.flush()
    item_id = item.id

    await delete_menu_item(item_id, admin=admin, db=db)
    await db.commit()

    assert await db.get(MenuItem, item_id) is None


async def test_delete_retires_item_with_order_history(db):
    """An item referenced by past orders is hidden, not destroyed."""
    from app.routers.admin import delete_menu_item

    admin = User(email="a@example.com", role=UserRole.admin)
    member = User(email="m@example.com", role=UserRole.member)
    item = MenuItem(name_he="חומוס ותיק", category="hummus", price_agorot=4200)
    db.add_all([admin, member, item])
    await db.flush()

    order = Order(order_number="PH-TEST-0001", user_id=member.id)
    db.add(order)
    await db.flush()
    db.add(
        OrderItem(
            order_id=order.id,
            menu_item_id=item.id,
            name_snapshot=item.name_he,
            unit_price_agorot=item.price_agorot,
            quantity=1,
            line_total_agorot=item.price_agorot,
        )
    )
    await db.flush()
    item_id = item.id

    await delete_menu_item(item_id, admin=admin, db=db)
    await db.commit()

    survivor = await db.get(MenuItem, item_id)
    assert survivor is not None, "row backing order history must survive"
    assert survivor.is_available is False, "but it must disappear from the menu"


async def test_delete_missing_item_is_404(db):
    from app.routers.admin import delete_menu_item

    admin = User(email="a@example.com", role=UserRole.admin)
    db.add(admin)
    await db.flush()

    with pytest.raises(HTTPException) as exc:
        await delete_menu_item(999999, admin=admin, db=db)
    assert exc.value.status_code == 404


def test_remove_media_ignores_paths_outside_media_root(tmp_path, monkeypatch):
    """A crafted image_url must not delete files elsewhere on disk."""
    from app.routers import admin as admin_mod

    media = tmp_path / "media" / "menu"
    media.mkdir(parents=True)
    monkeypatch.setattr(admin_mod, "MEDIA_ROOT", media)

    victim = tmp_path / "important.txt"
    victim.write_text("do not delete")

    admin_mod._remove_media("/media/menu/../../important.txt")
    assert victim.exists(), "traversal must not escape MEDIA_ROOT"

    legit = media / "7-abc.png"
    legit.write_bytes(_png_bytes())
    admin_mod._remove_media("/media/menu/7-abc.png")
    assert not legit.exists()
