"""Inline keyboard builders."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


# ---- Main menu ----

def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🥞 Create a new party", callback_data="create_party")],
            [InlineKeyboardButton("📋 My parties", callback_data="my_parties")],
        ]
    )


# ---- Party menu ----

def party_menu_keyboard(party_id: int, is_admin: bool = False, is_owner: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("ℹ️ Party info", callback_data=f"party_info:{party_id}")],
        [InlineKeyboardButton("📜 View fillings", callback_data=f"view_fillings:{party_id}")],
        [InlineKeyboardButton("➕ Add filling", callback_data=f"add_filling:{party_id}")],
        [InlineKeyboardButton("✏️ Edit my fillings", callback_data=f"edit_fillings:{party_id}")],
        [InlineKeyboardButton("👥 Members", callback_data=f"members:{party_id}")],
        [InlineKeyboardButton("🔗 Invite link", callback_data=f"invite_link:{party_id}")],
    ]
    if is_admin:
        buttons.append([InlineKeyboardButton("🚫 Cancel party", callback_data=f"cancel_party:{party_id}")])
    if not is_owner:
        buttons.append([InlineKeyboardButton("🚪 Leave party", callback_data=f"leave_party:{party_id}")])
    buttons.append([InlineKeyboardButton("⬅️ Back to my parties", callback_data="my_parties")])
    return InlineKeyboardMarkup(buttons)


# ---- Party list (my parties) ----

def parties_list_keyboard(parties: list[dict], user_id: int) -> InlineKeyboardMarkup:
    buttons = []
    for p in parties:
        label = f"🥞 {p['name']}"
        creator_name = p.get("creator_name")
        if creator_name and p["creator_id"] != user_id:
            label += f"  ({creator_name})"
        buttons.append([InlineKeyboardButton(label, callback_data=f"open_party:{p['id']}")])
    buttons.append([InlineKeyboardButton("⬅️ Main menu", callback_data="main_menu")])
    return InlineKeyboardMarkup(buttons)


# ---- Party info ----

def party_info_keyboard(party_id: int, is_admin: bool = False) -> InlineKeyboardMarkup:
    buttons = []
    if is_admin:
        buttons.append([InlineKeyboardButton("✏️ Edit info", callback_data=f"edit_party_info:{party_id}")])
    buttons.append([InlineKeyboardButton("⬅️ Back to party", callback_data=f"open_party:{party_id}")])
    return InlineKeyboardMarkup(buttons)


def edit_info_keyboard(party_id: int, info: dict) -> InlineKeyboardMarkup:
    """Keyboard for choosing which info field to edit. Shows 'Clear' hint if field is set."""
    fields = [
        ("info_datetime", "🕐 Date & time"),
        ("info_address", "📍 Address"),
        ("info_map_link", "🗺 Map link"),
        ("info_description", "📝 Description"),
    ]
    buttons = []
    for field_key, label in fields:
        current = info.get(field_key)
        btn_label = f"{label} ✅" if current else label
        buttons.append([InlineKeyboardButton(btn_label, callback_data=f"set_info:{party_id}:{field_key}")])
    buttons.append([InlineKeyboardButton("⬅️ Back to info", callback_data=f"party_info:{party_id}")])
    return InlineKeyboardMarkup(buttons)


def time_picker_keyboard(party_id: int) -> InlineKeyboardMarkup:
    """Grid of hour buttons for time selection (10:00–22:00), 3 per row."""
    hours = list(range(10, 23))
    buttons = []
    row = []
    for h in hours:
        row.append(InlineKeyboardButton(f"{h:02d}:00", callback_data=f"pick_time:{party_id}:{h}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data=f"edit_party_info:{party_id}")])
    return InlineKeyboardMarkup(buttons)


def edit_info_field_keyboard(party_id: int, field: str, has_value: bool) -> InlineKeyboardMarkup:
    """Keyboard shown when editing a single info field. Offers clear if value exists."""
    buttons = []
    if has_value:
        buttons.append([InlineKeyboardButton("🗑 Clear this field", callback_data=f"clear_info:{party_id}:{field}")])
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data=f"edit_party_info:{party_id}")])
    return InlineKeyboardMarkup(buttons)


# ---- Fillings list ----

def fillings_list_keyboard(party_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Add filling", callback_data=f"add_filling:{party_id}")],
            [InlineKeyboardButton("⬅️ Back to party", callback_data=f"open_party:{party_id}")],
        ]
    )


# ---- User fillings (for edit) ----

def user_fillings_keyboard(fillings: list[dict], party_id: int) -> InlineKeyboardMarkup:
    buttons = []
    for f in fillings:
        buttons.append(
            [
                InlineKeyboardButton(
                    f"✏️ {f['name']}",
                    callback_data=f"edit_one_filling:{f['id']}",
                ),
            ]
        )
    buttons.append([InlineKeyboardButton("⬅️ Back to party", callback_data=f"open_party:{party_id}")])
    return InlineKeyboardMarkup(buttons)


# ---- Single filling edit ----

def edit_filling_keyboard(filling_id: int, party_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✏️ Rename", callback_data=f"rename_filling:{filling_id}")],
            [InlineKeyboardButton("🗑 Remove", callback_data=f"remove_filling:{filling_id}")],
            [InlineKeyboardButton("⬅️ Back", callback_data=f"edit_fillings:{party_id}")],
        ]
    )


# ---- Leave party confirmation ----

def confirm_leave_keyboard(party_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Yes, leave", callback_data=f"confirm_leave:{party_id}")],
            [InlineKeyboardButton("⬅️ No, go back", callback_data=f"open_party:{party_id}")],
        ]
    )


# ---- Members ----

def members_keyboard(party_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Search member", callback_data=f"search_member:{party_id}")],
        [InlineKeyboardButton("⬅️ Back to party", callback_data=f"open_party:{party_id}")],
    ])


# ---- Admin members list (with manage buttons) ----

def admin_members_keyboard(members: list[dict], party_id: int, viewer_id: int) -> InlineKeyboardMarkup:
    """Build keyboard for admin member management.

    viewer_id is the telegram_id of the user viewing this list.
    Only the party owner (creator) can promote/demote. All admins can kick.
    """
    buttons = []
    for m in members:
        if m["telegram_id"] == viewer_id:
            # Don't show buttons for yourself
            continue
        row = []
        if m.get("is_admin"):
            row.append(InlineKeyboardButton(
                f"⬇️ {m['telegram_name']}",
                callback_data=f"demote_admin:{party_id}:{m['telegram_id']}",
            ))
        else:
            row.append(InlineKeyboardButton(
                f"⬆️ {m['telegram_name']}",
                callback_data=f"promote_admin:{party_id}:{m['telegram_id']}",
            ))
        row.append(InlineKeyboardButton(
            f"❌",
            callback_data=f"kick_member:{party_id}:{m['telegram_id']}",
        ))
        buttons.append(row)
    buttons.append([InlineKeyboardButton("⬅️ Back to party", callback_data=f"open_party:{party_id}")])
    return InlineKeyboardMarkup(buttons)


# ---- Confirm kick ----

def confirm_kick_keyboard(party_id: int, telegram_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Yes, remove", callback_data=f"confirm_kick:{party_id}:{telegram_id}")],
            [InlineKeyboardButton("⬅️ No, go back", callback_data=f"members:{party_id}")],
        ]
    )


# ---- Cancel party confirmation ----

def confirm_cancel_party_keyboard(party_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Yes, cancel the party", callback_data=f"confirm_cancel_party:{party_id}")],
            [InlineKeyboardButton("⬅️ No, go back", callback_data=f"open_party:{party_id}")],
        ]
    )


# ---- Cancel (used during text input flows) ----

def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Cancel", callback_data="cancel")]]
    )
