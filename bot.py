import logging
import os
import json
import qrcode
import io
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    InputMediaPhoto
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from database import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ADMIN_ID = int(os.getenv("ADMIN_ID", "6198353113"))

# States
WAITING_PAYMENT_SS = 1
WAITING_BROADCAST = 2

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_user(user.id, user.username or user.first_name)
    
    settings = db.get_settings()
    
    keyboard = [
        [InlineKeyboardButton("💎 Unlock Premium", callback_data="unlock_premium")],
        [InlineKeyboardButton("🎬 Demo Videos", callback_data="demo_videos")],
        [InlineKeyboardButton("✅ How To Get Premium", callback_data="how_to_get")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    start_text = settings.get("start_text", "Welcome! Choose an option below 👇")
    start_image = settings.get("start_image", None)
    
    if start_image:
        await update.message.reply_photo(
            photo=start_image,
            caption=start_text,
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            start_text,
            reply_markup=reply_markup
        )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    settings = db.get_settings()

    if data == "unlock_premium":
        await show_plans(query, context)

    elif data == "demo_videos":
        demo_videos = db.get_demo_videos()
        if not demo_videos:
            await query.message.reply_text("No demo videos available yet.")
            return
        for video in demo_videos:
            try:
                await query.message.reply_video(
                    video=video["file_id"],
                    caption="🎬 Demo Video\n\n💎 Click Get Premium for VIP channels access"
                )
            except:
                await query.message.reply_text("This video is only for demo\n💎 Click Get Premium for VIP channels access")
        keyboard = [[InlineKeyboardButton("👉 Get Premium", callback_data="unlock_premium")]]
        await query.message.reply_text("This video is only for demo\n💎 Click Get Premium for VIP channels access",
                                        reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "how_to_get":
        text = (
            "✅ *How To Get Premium*\n\n"
            "1️⃣ Click *Unlock Premium*\n"
            "2️⃣ Choose your plan\n"
            "3️⃣ Scan QR code & pay\n"
            "4️⃣ Click *PAYMENT DONE* & send screenshot\n"
            "5️⃣ Wait for approval (within 20 mins)\n"
            "6️⃣ Get your private channel link! 🎉"
        )
        keyboard = [[InlineKeyboardButton("💎 Get Premium", callback_data="unlock_premium")]]
        await query.message.reply_text(text, parse_mode="Markdown",
                                        reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("plan_"):
        plan_key = data  # e.g. plan_1, plan_2, plan_3, plan_4
        plans = settings.get("plans", {})
        plan = plans.get(plan_key, {})
        price = plan.get("price", 99)
        plan_name = plan.get("name", "Premium")
        upi_id = settings.get("upi_id", "yourname@upi")
        
        # Generate QR code
        upi_url = f"upi://pay?pa={upi_id}&pn=Premium&am={price}&cu=INR"
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(upi_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        
        context.user_data["selected_plan"] = plan_key
        context.user_data["selected_price"] = price
        context.user_data["selected_plan_name"] = plan_name
        
        keyboard = [
            [InlineKeyboardButton("✅ PAYMENT DONE - SEND SCREENSHOT", callback_data="payment_done")]
        ]
        
        premium_photo = settings.get("premium_photo", None)
        caption = (
            f"💰 *Price: ₹{price}*\n"
            f"⏳ *Time Left: 02:00*\n\n"
            f"1️⃣ Scan | 2️⃣ Pay | 3️⃣ Click 'PAYMENT DONE'\n\n"
            f"📲 UPI ID: `{upi_id}`"
        )
        
        await query.message.reply_photo(
            photo=buf,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "payment_done":
        await query.message.reply_text(
            "📸 *SEND SCREENSHOT OF YOUR PAYMENT FOR GET PREMIUM*",
            parse_mode="Markdown"
        )
        context.user_data["awaiting_ss"] = True

    elif data.startswith("approve_"):
        user_id = int(data.split("_")[1])
        payment_id = data.split("_")[2]
        settings = db.get_settings()
        private_link = settings.get("private_link", "https://t.me/+example")
        
        db.update_payment(payment_id, "approved")
        
        approval_photo = settings.get("approval_photo", None)
        approval_text = settings.get("approval_text", 
            f"✅ *Payment Approved!*\n\n🎉 Welcome to Premium!\n\n🔗 Your private channel link:\n{private_link}")
        
        try:
            if approval_photo:
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=approval_photo,
                    caption=approval_text,
                    parse_mode="Markdown"
                )
            else:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=approval_text,
                    parse_mode="Markdown"
                )
        except:
            pass
        
        await query.message.reply_text(f"✅ Payment approved and link sent to user {user_id}!")

    elif data.startswith("reject_"):
        user_id = int(data.split("_")[1])
        payment_id = data.split("_")[2]
        db.update_payment(payment_id, "rejected")
        
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ *Payment Rejected*\n\nYour payment screenshot was not verified. Please try again or contact support.",
                parse_mode="Markdown"
            )
        except:
            pass
        
        await query.message.reply_text(f"❌ Payment rejected for user {user_id}!")

    elif data.startswith("fake_"):
        user_id = int(data.split("_")[1])
        payment_id = data.split("_")[2]
        db.update_payment(payment_id, "fake")
        
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="⚠️ *Fake Payment Detected*\n\nYour payment appears to be fake. Please make a real payment or you may be banned.",
                parse_mode="Markdown"
            )
        except:
            pass
        
        await query.message.reply_text(f"⚠️ Fake payment marked for user {user_id}!")

async def show_plans(query, context):
    settings = db.get_settings()
    plans = settings.get("plans", {
        "plan_1": {"name": "Basic", "price": 59},
        "plan_2": {"name": "Standard", "price": 99},
        "plan_3": {"name": "Premium", "price": 149},
        "plan_4": {"name": "VIP", "price": 199},
    })
    
    premium_photo = settings.get("premium_photo", None)
    
    keyboard = []
    for key, plan in plans.items():
        keyboard.append([InlineKeyboardButton(
            f"{'⭐ MOST POPULAR - ' if plan['price'] == 149 else ''}₹{plan['price']}/- {plan['name']}",
            callback_data=key
        )])
    
    text = "💎 *Choose Your Plan*\n\n✅ Trusted Seller\n📦 ALL IN ONE 50+ GROUPS"
    
    if premium_photo:
        await query.message.reply_photo(
            photo=premium_photo,
            caption=text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await query.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message

    # Handle payment screenshot
    if context.user_data.get("awaiting_ss") and (message.photo or message.document):
        context.user_data["awaiting_ss"] = False
        
        if message.photo:
            file_id = message.photo[-1].file_id
        else:
            file_id = message.document.file_id
        
        plan_name = context.user_data.get("selected_plan_name", "Unknown")
        price = context.user_data.get("selected_price", "?")
        
        payment_id = db.add_payment(user.id, plan_name, price, file_id)
        
        # Send pending message to user
        await message.reply_text(
            "📋 *Payment Sent For Approval*\n\n⏳ Pending approval...\n\n"
            "✅ Screenshot has been sent for approval\n"
            "You will get private channel link within 20 minutes\n"
            "Contact support if needed",
            parse_mode="Markdown"
        )
        
        # Send to admin for approval
        keyboard = [
            [
                InlineKeyboardButton("✅ APPROVE", callback_data=f"approve_{user.id}_{payment_id}"),
                InlineKeyboardButton("❌ REJECT", callback_data=f"reject_{user.id}_{payment_id}")
            ],
            [InlineKeyboardButton("⚠️ FAKE PAYMENT", callback_data=f"fake_{user.id}_{payment_id}")]
        ]
        
        caption = (
            f"💰 *New Payment Request*\n\n"
            f"👤 User: {user.first_name} (@{user.username or 'N/A'})\n"
            f"🆔 User ID: `{user.id}`\n"
            f"📦 Plan: {plan_name}\n"
            f"💵 Amount: ₹{price}"
        )
        
        await context.bot.send_photo(
            chat_id=ADMIN_ID,
            photo=file_id,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Admin panel commands
    if user.id == ADMIN_ID:
        await handle_admin_message(update, context)

async def handle_admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    context_data = context.user_data
    
    if context_data.get("setting") == "start_text":
        db.update_setting("start_text", message.text)
        context_data.clear()
        await message.reply_text("✅ Start text updated!")

    elif context_data.get("setting") == "start_image":
        if message.photo:
            db.update_setting("start_image", message.photo[-1].file_id)
            context_data.clear()
            await message.reply_text("✅ Start image updated!")
        else:
            await message.reply_text("Please send a photo!")

    elif context_data.get("setting") == "premium_photo":
        if message.photo:
            db.update_setting("premium_photo", message.photo[-1].file_id)
            context_data.clear()
            await message.reply_text("✅ Premium photo updated!")
        else:
            await message.reply_text("Please send a photo!")

    elif context_data.get("setting") == "demo_video":
        if message.video:
            db.add_demo_video(message.video.file_id)
            context_data.clear()
            await message.reply_text("✅ Demo video added!")
        else:
            await message.reply_text("Please send a video!")

    elif context_data.get("setting") == "upi_id":
        db.update_setting("upi_id", message.text)
        context_data.clear()
        await message.reply_text(f"✅ UPI ID updated to: {message.text}")

    elif context_data.get("setting") == "private_link":
        db.update_setting("private_link", message.text)
        context_data.clear()
        await message.reply_text("✅ Private link updated!")

    elif context_data.get("setting") == "broadcast":
        context_data.clear()
        users = db.get_all_users()
        success = 0
        failed = 0
        for uid in users:
            try:
                if message.photo:
                    await message.bot.send_photo(chat_id=uid, photo=message.photo[-1].file_id,
                                                  caption=message.caption or "")
                elif message.video:
                    await message.bot.send_video(chat_id=uid, video=message.video.file_id,
                                                  caption=message.caption or "")
                else:
                    await message.bot.send_message(chat_id=uid, text=message.text)
                success += 1
            except:
                failed += 1
        await message.reply_text(f"📢 Broadcast done!\n✅ Sent: {success}\n❌ Failed: {failed}")

    elif context_data.get("setting", "").startswith("plan_price_"):
        plan_key = context_data["setting"].replace("plan_price_", "")
        try:
            price = int(message.text)
            settings = db.get_settings()
            plans = settings.get("plans", {})
            if plan_key not in plans:
                plans[plan_key] = {"name": plan_key, "price": price}
            else:
                plans[plan_key]["price"] = price
            db.update_setting("plans", plans)
            context_data.clear()
            await message.reply_text(f"✅ Plan {plan_key} price updated to ₹{price}!")
        except:
            await message.reply_text("Please send a valid number!")

    elif context_data.get("setting", "").startswith("plan_name_"):
        plan_key = context_data["setting"].replace("plan_name_", "")
        settings = db.get_settings()
        plans = settings.get("plans", {})
        if plan_key not in plans:
            plans[plan_key] = {"name": message.text, "price": 99}
        else:
            plans[plan_key]["name"] = message.text
        db.update_setting("plans", plans)
        context_data.clear()
        await message.reply_text(f"✅ Plan {plan_key} name updated to: {message.text}")

# ADMIN COMMANDS
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await show_admin_panel(update.message, context)

async def show_admin_panel(message, context):
    settings = db.get_settings()
    total_users = db.get_total_users()
    
    keyboard = [
        [InlineKeyboardButton("🖼 Set Start Image", callback_data="admin_start_image"),
         InlineKeyboardButton("📝 Set Start Text", callback_data="admin_start_text")],
        [InlineKeyboardButton("💎 Set Premium Photo", callback_data="admin_premium_photo"),
         InlineKeyboardButton("🎬 Add Demo Video", callback_data="admin_demo_video")],
        [InlineKeyboardButton("💳 Set UPI ID", callback_data="admin_set_upi"),
         InlineKeyboardButton("🔗 Set Private Link", callback_data="admin_set_link")],
        [InlineKeyboardButton("💰 Manage Plans", callback_data="admin_plans")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton(f"👥 Total Users: {total_users}", callback_data="admin_users")],
        [InlineKeyboardButton("🎬 View Demo Videos", callback_data="admin_view_demos"),
         InlineKeyboardButton("🗑 Clear Demo Videos", callback_data="admin_clear_demos")],
    ]
    
    upi = settings.get("upi_id", "Not set")
    link = settings.get("private_link", "Not set")
    
    await message.reply_text(
        f"🛠 *Admin Panel*\n\n"
        f"👥 Total Users: `{total_users}`\n"
        f"💳 UPI ID: `{upi}`\n"
        f"🔗 Private Link: `{link}`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("Not authorized!")
        return
    
    await query.answer()
    data = query.data
    
    if data == "admin_start_image":
        context.user_data["setting"] = "start_image"
        await query.message.reply_text("📸 Send the new start image (photo):")
    
    elif data == "admin_start_text":
        context.user_data["setting"] = "start_text"
        await query.message.reply_text("📝 Send the new start text:")
    
    elif data == "admin_premium_photo":
        context.user_data["setting"] = "premium_photo"
        await query.message.reply_text("💎 Send the premium plans photo:")
    
    elif data == "admin_demo_video":
        context.user_data["setting"] = "demo_video"
        await query.message.reply_text("🎬 Send a demo video:")
    
    elif data == "admin_set_upi":
        context.user_data["setting"] = "upi_id"
        await query.message.reply_text("💳 Send your UPI ID (e.g. name@paytm):")
    
    elif data == "admin_set_link":
        context.user_data["setting"] = "private_link"
        await query.message.reply_text("🔗 Send the private channel link (e.g. https://t.me/+xxxx):")
    
    elif data == "admin_broadcast":
        context.user_data["setting"] = "broadcast"
        await query.message.reply_text("📢 Send your broadcast message (text, photo, or video):")
    
    elif data == "admin_users":
        users = db.get_all_users()
        total = len(users)
        await query.message.reply_text(f"👥 Total Users: *{total}*", parse_mode="Markdown")
    
    elif data == "admin_plans":
        settings = db.get_settings()
        plans = settings.get("plans", {
            "plan_1": {"name": "Basic", "price": 59},
            "plan_2": {"name": "Standard", "price": 99},
            "plan_3": {"name": "Most Popular", "price": 149},
            "plan_4": {"name": "VIP", "price": 199},
        })
        keyboard = []
        for key, plan in plans.items():
            keyboard.append([
                InlineKeyboardButton(f"✏️ {plan['name']} - ₹{plan['price']}", callback_data=f"edit_plan_{key}")
            ])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_back")])
        await query.message.reply_text("💰 *Manage Plans:*", parse_mode="Markdown",
                                        reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data.startswith("edit_plan_"):
        plan_key = data.replace("edit_plan_", "")
        keyboard = [
            [InlineKeyboardButton("✏️ Change Price", callback_data=f"set_plan_price_{plan_key}")],
            [InlineKeyboardButton("✏️ Change Name", callback_data=f"set_plan_name_{plan_key}")],
            [InlineKeyboardButton("🔙 Back", callback_data="admin_plans")]
        ]
        await query.message.reply_text(f"Edit plan *{plan_key}*:", parse_mode="Markdown",
                                        reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data.startswith("set_plan_price_"):
        plan_key = data.replace("set_plan_price_", "")
        context.user_data["setting"] = f"plan_price_{plan_key}"
        await query.message.reply_text(f"💰 Send new price for {plan_key} (numbers only, e.g. 99):")
    
    elif data.startswith("set_plan_name_"):
        plan_key = data.replace("set_plan_name_", "")
        context.user_data["setting"] = f"plan_name_{plan_key}"
        await query.message.reply_text(f"✏️ Send new name for {plan_key}:")
    
    elif data == "admin_view_demos":
        videos = db.get_demo_videos()
        if not videos:
            await query.message.reply_text("No demo videos saved.")
        else:
            await query.message.reply_text(f"🎬 Total demo videos: {len(videos)}")
    
    elif data == "admin_clear_demos":
        db.clear_demo_videos()
        await query.message.reply_text("✅ All demo videos cleared!")
    
    elif data == "admin_back":
        await show_admin_panel(query.message, context)

def main():
    token = os.getenv("BOT_TOKEN", "8694328725:AAHLoHqcmnzzAVhuMlrY_vTUnFZcv6QJX9g")
    
    app = Application.builder().token(token).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(admin_button_handler, pattern="^admin_"))
    app.add_handler(CallbackQueryHandler(admin_button_handler, pattern="^edit_plan_"))
    app.add_handler(CallbackQueryHandler(admin_button_handler, pattern="^set_plan_"))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    
    print("Bot is running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
