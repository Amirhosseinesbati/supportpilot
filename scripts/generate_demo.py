"""Generate deterministic, isolated SupportPilot demo and evaluation data.

All names and identifiers are fictional. This script uses the standard library only.
The large JSON is generated locally; only the small fixture needs to be checked in.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEED = 240917
DEFAULT_REFERENCE_DATE = date(2026, 9, 27)
PASSWORD = "DemoPass!2026"
FIRST_NAMES = (
    "Avery", "Blair", "Casey", "Devon", "Ellis", "Finley", "Gray", "Harper",
    "Indigo", "Jules", "Kai", "Lane", "Morgan", "Noel", "Oakley", "Parker",
    "Quinn", "Reese", "Sage", "Taylor", "Uma", "Val", "Wren", "Zion",
)
LAST_NAMES = (
    "Arden", "Bell", "Chen", "Diaz", "Everett", "Farah", "Grant", "Hale",
    "Ibrahim", "Jensen", "Khan", "Lin", "Morales", "Nouri", "Olsen", "Patel",
    "Reed", "Sato", "Torres", "Usman", "Vega", "White", "Xu", "Young",
)

# Category, product noun, base price, useful specifications. Values vary by model.
PRODUCT_FAMILIES: tuple[tuple[str, str, int], ...] = (
    ("monitor", "Display", 37900),
    ("desk", "Sit-Stand Desk", 69900),
    ("chair", "Task Chair", 48900),
    ("lamp", "Task Lamp", 12900),
    ("arm", "Monitor Arm", 17900),
    ("keyboard", "Keyboard", 14900),
    ("dock", "USB-C Dock", 24900),
    ("storage", "Desk Storage", 8900),
    ("acoustic", "Acoustic Panel", 21900),
    ("accessory", "Desk Accessory", 4900),
)
SERIES = ("Aster", "Beacon", "Cedar", "Drift", "Ember", "Field", "Grove", "Horizon", "Iris", "Juniper", "Kepler", "Lumen")
CARRIERS = ("Parcel North Test", "Blue Route Test", "Union Courier Test")


def timestamp(day: date, hour: int = 12) -> str:
    return datetime(day.year, day.month, day.day, hour, tzinfo=timezone.utc).isoformat()


def day_at(reference: date, days_ago: int) -> date:
    return reference - timedelta(days=days_ago)


def first_day_of_twelve_month_window(reference: date) -> date:
    month_index = reference.year * 12 + reference.month - 1 - 11
    return date(month_index // 12, month_index % 12 + 1, 1)


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def product_specs(category: str, number: int) -> dict[str, str]:
    variation = number % 4
    if category == "monitor":
        return {
            "size_in": str((24, 27, 32, 34)[variation]),
            "resolution": ("1920 × 1080", "2560 × 1440", "3840 × 2160", "3440 × 1440")[variation],
            "refresh_hz": str((75, 100, 60, 100)[variation]),
            "vesa_mm": ("75 × 75", "100 × 100", "100 × 100", "100 × 100")[variation],
            "power_w": str(31 + number * 2),
        }
    if category == "desk":
        return {
            "width_cm": str((120, 140, 160, 180)[variation]),
            "depth_cm": str((60, 70, 75, 80)[variation]),
            "height_range_cm": f"{62 + variation}–{126 + variation}",
            "load_kg": str(70 + variation * 10),
            "surface": ("birch laminate", "walnut veneer", "matte white laminate", "ash veneer")[variation],
        }
    if category == "chair":
        return {
            "seat_height_cm": f"{41 + variation}–{52 + variation}",
            "load_kg": str(110 + variation * 10),
            "armrests": ("fixed", "2D adjustable", "3D adjustable", "4D adjustable")[variation],
            "back": ("mesh", "woven fabric", "mesh", "recycled knit")[variation],
        }
    if category == "lamp":
        return {"brightness_lm": str(550 + number * 35), "color_temperature_k": "2700–5000", "power_w": str(7 + variation), "clamp_max_mm": str(45 + variation * 5)}
    if category == "arm":
        return {"screen_size_in": f"17–{32 + variation * 2}", "load_kg": f"2–{8 + variation}", "vesa_mm": "75 × 75; 100 × 100", "clamp_max_mm": str(55 + variation * 5)}
    if category == "keyboard":
        return {"layout": ("US ANSI", "UK ISO", "US ANSI", "compact US ANSI")[variation], "connection": ("USB-C", "Bluetooth/USB-C", "2.4 GHz/USB-C", "Bluetooth/USB-C")[variation], "battery_hours": str(80 + number * 8)}
    if category == "dock":
        return {"host_port": "USB-C", "display_output": ("single 4K 60 Hz", "dual 4K 30 Hz", "dual 4K 60 Hz", "single 5K 60 Hz")[variation], "power_delivery_w": str((65, 85, 100, 100)[variation]), "ethernet": "1 Gb/s"}
    if category == "storage":
        return {"width_cm": str(28 + variation * 6), "depth_cm": str(18 + variation * 3), "material": ("powder-coated steel", "bamboo", "recycled felt", "solid ash")[variation], "max_load_kg": str(8 + variation * 2)}
    if category == "acoustic":
        return {"size_cm": ("60 × 60", "60 × 120", "80 × 120", "100 × 120")[variation], "thickness_mm": str(20 + variation * 5), "material": "recycled PET felt", "mounting": ("wall adhesive", "wall screws", "desk clamp", "wall screws")[variation]}
    return {"length_cm": str(25 + variation * 5), "material": ("aluminum", "bamboo", "recycled polymer", "silicone")[variation], "finish": ("graphite", "natural", "sand", "navy")[variation]}


def build_products() -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    for family_index, (category, noun, base_price) in enumerate(PRODUCT_FAMILIES):
        for number in range(1, 13):
            workspace = "ws_northstar" if number <= 9 else "ws_harbor"
            prefix = "ns" if workspace == "ws_northstar" else "hb"
            local_number = number if prefix == "ns" else number - 9
            product_id = "prod_ns_demo_monitor" if category == "monitor" and number == 1 else f"prod_{prefix}_{category}_{local_number:02d}"
            products.append({
                "id": product_id,
                "workspace_id": workspace,
                "sku": f"{prefix.upper()}-{category[:3].upper()}-{local_number:03d}",
                "name": f"{SERIES[family_index]} {noun} {number:02d}",
                "category": category,
                "price_cents": base_price + (number - 1) * (1900 if base_price > 20000 else 700),
                "currency": "USD",
                "specifications": product_specs(category, number),
                "active": True,
            })
    return products


def build_customers() -> list[dict[str, Any]]:
    customers: list[dict[str, Any]] = []
    for prefix, workspace, count in (("ns", "ws_northstar", 640), ("hb", "ws_harbor", 160)):
        for number in range(1, count + 1):
            ident = "cust_ns_demo_001" if prefix == "ns" and number == 1 else f"cust_{prefix}_{number:04d}"
            first = FIRST_NAMES[(number * 7 + (0 if prefix == "ns" else 5)) % len(FIRST_NAMES)]
            last = LAST_NAMES[(number * 11 + (0 if prefix == "ns" else 3)) % len(LAST_NAMES)]
            customers.append({
                "id": ident,
                "workspace_id": workspace,
                "name": f"{first} {last}",
                "email": f"{prefix}.customer.{number:04d}@example.test",
                "phone": None if number % 7 == 0 else f"+1-555-01{number % 100:02d}",
                "created_at": timestamp(date(2024, 1, 1) + timedelta(days=(number * 13) % 480)),
                "locale": "en-US",
            })
    return customers


def build_users(customers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    users: list[dict[str, Any]] = []
    for prefix, workspace, company in (("ns", "ws_northstar", "Northstar"), ("hb", "ws_harbor", "Harbor")):
        for role, name in (("admin", "Admin"), ("operator", "Operator"), ("viewer", "Viewer")):
            users.append({"id": f"user_{prefix}_{role}", "workspace_id": workspace, "customer_id": None,
                          "email": f"{role}.{prefix}@example.test", "name": f"{company} {name}", "role": role, "password": PASSWORD})
        owned = [customer for customer in customers if customer["workspace_id"] == workspace]
        for index, customer in enumerate(owned, 1):
            users.append({
                "id": "user_ns_demo_customer" if prefix == "ns" and index == 1 else f"user_{prefix}_customer_{index:02d}",
                "workspace_id": workspace,
                "customer_id": customer["id"],
                "email": customer["email"],
                "name": customer["name"],
                "role": "customer",
                "password": PASSWORD,
            })
    return users


def build_workspaces(reference: date) -> list[dict[str, Any]]:
    policy_start = (reference - timedelta(days=179)).isoformat()
    return [
        {"id": "ws_northstar", "slug": "northstar", "name": "Northstar Supply", "currency": "USD",
         "demo": True, "return_policy": {"standard_days": 30, "monitor_days": 21,
             "late_delivery_grace_days": 45, "late_threshold_days": 7,
             "exception_requires_review": True, "effective_from": policy_start},
         "support_email": "support@northstar.example.test", "reference_date": reference.isoformat()},
        {"id": "ws_harbor", "slug": "harbor", "name": "Harbor Workroom", "currency": "USD",
         "demo": True, "return_policy": {"standard_days": 21, "monitor_days": 14,
             "late_delivery_grace_days": 35, "late_threshold_days": 10,
             "exception_requires_review": True, "effective_from": policy_start},
         "support_email": "support@harbor.example.test", "reference_date": reference.isoformat()},
    ]


def build_orders(products: list[dict[str, Any]], customers: list[dict[str, Any]], reference: date, rng: random.Random) -> list[dict[str, Any]]:
    by_workspace_products = {ws: [item for item in products if item["workspace_id"] == ws] for ws in ("ws_northstar", "ws_harbor")}
    by_workspace_customers = {ws: [item for item in customers if item["workspace_id"] == ws] for ws in ("ws_northstar", "ws_harbor")}
    orders: list[dict[str, Any]] = []
    history_days = (reference - first_day_of_twelve_month_window(reference)).days
    for prefix, workspace, count in (("ns", "ws_northstar", 2400), ("hb", "ws_harbor", 600)):
        catalog = by_workspace_products[workspace]
        customer_pool = by_workspace_customers[workspace]
        for number in range(1, count + 1):
            hero = prefix == "ns" and number == 1
            order_id = "ord_ns_demo_001" if hero else f"ord_{prefix}_{number:05d}"
            customer = customer_pool[0] if hero else rng.choice(customer_pool)
            placed = reference - timedelta(days=57) if hero else day_at(reference, rng.randint(0, history_days))
            chosen = [catalog[0]] if hero else rng.sample(catalog, k=rng.choices((1, 2, 3), weights=(66, 27, 7))[0])
            lines = []
            for line_index, product in enumerate(chosen, 1):
                quantity = 1 if hero else rng.choices((1, 2, 3), weights=(87, 11, 2))[0]
                lines.append({
                    "id": "line_ns_demo_001" if hero else f"line_{prefix}_{number:05d}_{line_index}",
                    "product_id": product["id"], "quantity": quantity,
                    "unit_price_cents": product["price_cents"], "returned_quantity": 0,
                })
            age = (reference - placed).days
            if hero:
                status = "delivered"
                shipped = placed + timedelta(days=9)
                delivered = placed + timedelta(days=25)
                promised = placed + timedelta(days=13)
            elif rng.random() < 0.035:
                status, shipped, delivered = "cancelled", None, None
                promised = placed + timedelta(days=7)
            elif age < 3:
                status, shipped, delivered = "processing", None, None
                promised = placed + timedelta(days=7)
            elif age < 11 and rng.random() < 0.62:
                status, shipped, delivered = "in_transit", placed + timedelta(days=1), None
                promised = placed + timedelta(days=7)
            else:
                shipped = placed + timedelta(days=rng.randint(1, 3))
                transit = rng.choices((2, 3, 4, 5, 7, 10, 14), weights=(10, 20, 25, 20, 15, 7, 3))[0]
                delivered = min(shipped + timedelta(days=transit), reference)
                promised = placed + timedelta(days=7)
                status = "delivered"
            shipment = [{
                "id": f"ship_{prefix}_{number:05d}", "status": status,
                "carrier": CARRIERS[number % len(CARRIERS)] if shipped else None,
                "tracking_code": f"{prefix.upper()}-TEST-{number:07d}" if shipped else None,
                "shipped_at": timestamp(shipped, 16) if shipped else None,
                "delivered_at": timestamp(delivered, 17) if delivered else None,
                "promised_delivery_at": timestamp(promised, 17),
            }]
            returns = []
            if not hero and status == "delivered" and (reference - delivered).days > 5 and rng.random() < 0.065:
                line = lines[0]
                returned = 1
                line["returned_quantity"] = returned
                return_day = delivered + timedelta(days=min(15, max(1, (reference - delivered).days // 2)))
                returns.append({"id": f"return_{prefix}_{number:05d}_1", "line_id": line["id"],
                                "quantity": returned, "status": "recorded", "created_at": timestamp(return_day, 11),
                                "reason": rng.choice(("changed_mind", "damaged", "wrong_fit"))})
            orders.append({
                "id": order_id, "workspace_id": workspace, "customer_id": customer["id"],
                "number": f"{prefix.upper()}-{number:06d}", "placed_at": timestamp(placed, 10),
                "status": status, "total_cents": sum(line["unit_price_cents"] * line["quantity"] for line in lines),
                "currency": "USD", "lines": lines, "shipments": shipment, "returns": returns,
            })
    return orders


def policy_text(prefix: str, category: str, version: int, workspace: dict[str, Any]) -> str:
    company = workspace["name"]
    new = version == 2
    standard = workspace["return_policy"]["standard_days"] if new else (45 if prefix == "ns" else 30)
    monitor = workspace["return_policy"]["monitor_days"] if new else (30 if prefix == "ns" else 21)
    grace = workspace["return_policy"]["late_delivery_grace_days"] if new else (50 if prefix == "ns" else 40)
    threshold = workspace["return_policy"]["late_threshold_days"] + (0 if new else 3)
    major_warranty = 24 if new else 12
    minor_warranty = 12 if new else 6
    policy = {
        "shipping": (
            f"# Delivery service and delay handling\n\n{company} sends a tracking link after the carrier accepts the parcel. "
            "The promised delivery date on the order confirmation is an estimate; a tracking scan is not proof of delivery. "
            f"If the final delivered scan is {threshold} or more calendar days after the promised date, support records a late-delivery flag. "
            "An in-transit order cannot be returned because no item has been received. Check the latest carrier event, then offer an operator ticket when tracking has not moved for five business days. "
            "For split deliveries, cite the shipment covering the item in question. Never disclose tracking for an order belonging to another customer. "
            "Related documents: Returns and exceptions; Order access and verification."
        ),
        "returns": (
            f"# Returns and late-delivery exceptions\n\nFor purchases delivered under {company}'s current policy, request a standard return within {standard} calendar days of the recorded delivery date. "
            f"Monitors have a {monitor}-day window because display panels require prompt inspection. Quantity requested cannot exceed purchased quantity less returns already recorded. "
            "Unopened items in saleable condition are eligible for a standard return; opened, damaged, incomplete, and uncertain-condition items require operator review. "
            f"When the delivered scan is at least {threshold} calendar days later than promised, a monitor request made within {grace} calendar days of delivery may be drafted as a late-delivery exception for operator review. "
            "A draft is not an approval or refund. An operator can approve, edit, reject, or allow it to expire; the approved version is the one executed. "
            "No money movement occurs in this pilot. Related documents: Delivery service and delay handling; Product inspection guide."
        ),
        "warranty": (
            f"# Limited product warranty\n\n{company} covers manufacturing defects for {major_warranty} months from delivery on desks, chairs, monitors, arms, and docks; lamps, keyboards, storage, acoustic panels, and accessories carry {minor_warranty} months. "
            "The warranty is tied to the original order and serial or lot identifier when one is supplied. Cosmetic wear, liquid damage, misuse, and modifications are excluded. "
            "A warranty claim is distinct from a discretionary return: a customer can ask about a defect after the return window closes. "
            "Support may collect photos and troubleshooting steps, but must not promise a replacement until an operator verifies coverage. "
            "Related documents: Troubleshooting checklist; Returns and late-delivery exceptions."
        ),
        "care": (
            "# Product care and cleaning\n\nDisconnect powered equipment before cleaning. Use a soft lint-free cloth with water on monitor panels; do not spray liquid onto ports or display edges. "
            "For laminated desk surfaces, wipe spills promptly and avoid abrasive cleaners. For mesh chairs, vacuum with a soft brush and spot-clean mild soap before use. "
            "Acoustic panels should be dusted rather than soaked because adhesive mounts can loosen with moisture. Follow the product manual when its material guidance is more specific. "
            "Damage from solvents or unapproved cleaners is outside the limited warranty. Related documents: Limited product warranty; individual product manuals."
        ),
        "assembly": (
            "# Assembly and first-use safety\n\nTwo adults should lift sit-stand desktops over 140 cm. Confirm all fasteners are seated before connecting the desk motor. "
            "Monitor arms must be clamped to a stable surface within the clamp thickness stated in the matching manual; do not mount to hollow or glass tops. "
            "Keep cable slack through the full desk height range and position power cords away from moving columns. "
            "If a carton is missing a fastener, note the bag code and order number for an operator; do not substitute an unverified screw. "
            "Related documents: Compatibility and fit; product manuals."
        ),
        "compatibility": (
            "# Compatibility and fit\n\nCheck both VESA hole pattern and supported weight before pairing an arm with a monitor. The arm's listed screen size alone does not establish fit. "
            "USB-C docks need a host port that supports DisplayPort alternate mode for video; a USB-C charging port by itself is insufficient. "
            "Use the relevant manual for exact dimensions, power delivery, and clamp range. If the customer's laptop or monitor model is not in the supplied evidence, ask for its specifications rather than guessing. "
            "Related documents: individual product manuals; Assembly and first-use safety."
        ),
        "payments": (
            "# Payments and receipts\n\nOrder totals in the support console are stored in USD cents and reflect the item prices at checkout. A support agent may explain a receipt but cannot take card details in chat. "
            "Do not request a password or full payment-card number. This pilot does not issue refunds or initiate payment adjustments. "
            "For a billing dispute, create an operator ticket with the order reference and redact sensitive card information. "
            "Related documents: Order access and verification; Returns and late-delivery exceptions."
        ),
        "accounts": (
            "# Order access and verification\n\nAn authenticated customer may view only orders bound to their server-side customer identity. An order number typed in a message never changes identity or authorizes a lookup. "
            "A guest uses the local verification challenge before any order detail is shown. Operators use role-bound console access and a workspace scope. "
            "If a customer quotes another person's order, decline the detail request and explain the verification step without confirming that the order exists. "
            "Related documents: Payments and receipts; Delivery service and delay handling."
        ),
        "troubleshooting": (
            "# Troubleshooting checklist\n\nFor a blank monitor, confirm power, input source, cable seating, and whether the computer detects the display. Record the exact model and whether its LED turns on. "
            "For a desk motor fault, remove obstructions, check the power brick and handset connector, then follow the manual's reset sequence without forcing a column. "
            "For a dock video issue, confirm the laptop USB-C port supports DisplayPort alternate mode and test one display at a time. "
            "Escalate electrical smell, exposed conductors, or an overheating power adapter immediately and advise the customer to disconnect power. "
            "Related documents: Limited product warranty; individual product manuals."
        ),
    }
    detail = {
        "shipping": "## Reading the timeline\nUse the order's promised date and the carrier's final delivered timestamp in calendar days. A tracking link can lag the carrier; when the two disagree, record both values and ask an operator to reconcile the delivery proof. Do not use a label-created timestamp as a shipped timestamp.",
        "returns": "## Decision record\nRecord the order line, purchased quantity, quantity already returned, item condition, delivered date, promised date, and applicable policy version. A late-delivery exception is reviewed by a person even when the dates meet the threshold. If evidence about condition or delivery is missing, request it before presenting the draft as eligible.",
        "warranty": "## Claim evidence\nAsk for the purchase reference, model, a concise symptom, and safe troubleshooting already attempted. An operator may request photos of the affected part but should avoid collecting unrelated personal details. The return deadline and warranty duration are independent clocks, so give each date separately when both are relevant.",
        "care": "## Material-specific check\nIf the manual names a finish or fabric, follow that material's care instruction first. Test any mild cleaner on a hidden area and let the material dry fully before reuse. A service ticket should distinguish a manufacturing defect from accidental staining or abrasive damage.",
        "assembly": "## Before escalating\nCheck the exact model and missing part or error code against its manual. Photograph the package label and affected step without exposing an address. If a moving desk binds or an electrical part overheats, stop use and create an operator ticket instead of repeating the reset procedure.",
        "compatibility": "## Evidence needed\nRecord the actual host device model, port capability, and any adapter in the signal path. For monitor mounting, record measured mass without stand and the VESA hole spacing. A broad family name does not establish compatibility; request the missing model or measurement.",
        "payments": "## Safe handling\nIf a customer posts card digits or a password, redact them from the support record and redirect to the approved payment channel. Store only the order reference and a summary of the disputed line item in the ticket. The local simulator records service actions but never moves funds.",
        "accounts": "## Guest access\nThe local guest challenge is a simulated verification step tied to a scoped customer record. A failed or absent challenge reveals neither order existence nor shipment details. The authenticated customer's identity comes from the server session and is rechecked whenever an order is read or an action is proposed.",
        "troubleshooting": "## Escalation packet\nCapture the product model, symptom, safe checks performed, their results, and whether the device can still be used. Avoid asking customers to open powered enclosures. If a model-specific manual offers a different sequence, cite the manual section and request operator help when the steps conflict.",
    }
    return policy[category] + "\n\n" + detail[category]


def manual_text(product: dict[str, Any], workspace: dict[str, Any]) -> str:
    specs = product["specifications"]
    category = product["category"]
    name = product["name"]
    specification_lines = "\n".join(f"- {key.replace('_', ' ').capitalize()}: {value}" for key, value in specs.items())
    setup = {
        "monitor": "Attach the stand while the panel rests face down on clean padding. Select the correct video input in the display menu, then set the computer to the listed native resolution. Leave ventilation slots clear and retain the carton for a damage claim.",
        "desk": "Lay out both legs and the frame before tightening the desktop. Connect the handset after the frame is upright. Run the full height range with loose cable loops before placing monitors on the surface.",
        "chair": "Fit the casters before lowering the seat onto the gas lift. Set the seat height so feet rest flat; adjust the armrests without lifting by them. Retighten accessible fasteners after the first month.",
        "lamp": "Seat the clamp on a flat, stable edge within the listed opening. Route the cord clear of pinch points. Start at a low brightness in a dark room and increase gradually.",
        "arm": "Check the monitor's actual mass and VESA pattern against the specifications below. Seat the clamp completely on solid material, then support the screen while tuning spring tension.",
        "keyboard": "Charge before first wireless pairing. For Bluetooth mode, hold the pairing key until its indicator pulses, then select this model in the operating system. USB-C provides wired input and charging.",
        "dock": "Connect the supplied power adapter before attaching peripherals. Verify that the laptop's host USB-C port supports video output. Connect one display first, then add a second within the stated display limit.",
        "storage": "Place the unit on a level desk and keep its heaviest contents low. Do not exceed the stated load. Felt or wood surfaces should be kept dry and wiped rather than soaked.",
        "acoustic": "Let the panel acclimate indoors for 24 hours. Clean and dry the mounting surface, then follow the listed mounting method. Check the wall substrate before choosing screw anchors.",
        "accessory": "Clean the desk surface before placement. Keep the accessory away from open flame and follow the material care note below. Inspect any adhesive periodically for lifting.",
    }[category]
    caution = {
        "monitor": "If the panel is cracked or emits a burning smell, disconnect it and open a support ticket. A single stuck pixel is assessed under the display inspection guide, not automatically a return approval.",
        "desk": "Do not operate the motor while a child is under the frame. A handset error should be recorded with its exact code; power cycling is safe only after checking for obstruction.",
        "chair": "Do not stand on the seat or use the armrests as lifting handles. Upholstery color may vary slightly by batch; ask for a photo if a defect is alleged.",
        "lamp": "Do not cover the LED head or use a damaged power supply. The dimmer remembers its last setting only while mains power is maintained.",
        "arm": "A glass or hollow-core desktop is not an approved clamp surface. If the monitor sags, support it before adjusting tension.",
        "keyboard": "A host that lacks Bluetooth can use the wired mode where supported. Do not promise an operating-system shortcut layout that is not listed in the manual.",
        "dock": "Some host USB-C ports provide charging but no video. If video fails, identify the laptop model and port specification before recommending a replacement.",
        "storage": "Keep liquids out of drawers and do not stack beyond the load rating. Surface marks from sharp objects are normal wear rather than a manufacturing defect.",
        "acoustic": "Adhesive mounting is intended for smooth painted surfaces. Textured plaster may require screw anchors and permission from the property owner.",
        "accessory": "Inspect for loose parts before use. Avoid harsh solvents and keep small components away from young children.",
    }[category]
    return (
        f"# {name} — Owner's manual\n\nModel: {product['sku']} | Category: {category} | {workspace['name']}\n\n"
        f"## Specifications\n{specification_lines}\n\n## Setup\n{setup}\n\n## Use and care\n{caution} "
        f"Keep the order number for support, but do not post it in a public forum. The {workspace['name']} care guide covers general cleaning.\n\n"
        "## Service path\nThe receipt's delivery date starts the return clock. Review the current Returns and late-delivery exceptions policy for category-specific windows. "
        "For a fault, record the symptom, power state, and steps tried before opening a warranty ticket. This manual does not itself authorize a return or replacement."
    )


def make_version(document_id: str, version: int, content: str, effective_from: str, effective_to: str | None, published_at: str) -> dict[str, Any]:
    sections = []
    heading = "Overview"
    body: list[str] = []
    for line in content.splitlines():
        if line.startswith("#"):
            if body:
                sections.append({"id": f"{document_id}_v{version}_s{len(sections) + 1}",
                                 "heading": heading, "page": 1 + len(sections) // 3,
                                 "text": "\n".join(body).strip()})
                body = []
            heading = line.lstrip("# ").strip()
        else:
            body.append(line)
    if body:
        sections.append({"id": f"{document_id}_v{version}_s{len(sections) + 1}",
                         "heading": heading, "page": 1 + len(sections) // 3,
                         "text": "\n".join(body).strip()})
    return {"id": f"{document_id}_v{version}", "version": version, "content": content,
            "sha256": content_hash(content), "effective_from": effective_from,
            "effective_to": effective_to, "published_at": published_at, "sections": sections}


def build_documents(products: list[dict[str, Any]], workspaces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    ws_by_id = {workspace["id"]: workspace for workspace in workspaces}
    for prefix, workspace_id in (("ns", "ws_northstar"), ("hb", "ws_harbor")):
        workspace = ws_by_id[workspace_id]
        reference = date.fromisoformat(workspace["reference_date"])
        history_start = first_day_of_twelve_month_window(reference)
        cutover = date.fromisoformat(workspace["return_policy"]["effective_from"])
        categories = ("shipping", "returns", "warranty", "care", "assembly", "compatibility", "payments", "accounts")
        if prefix == "ns":
            categories += ("troubleshooting",)
        for category in categories:
            doc_id = f"doc_{prefix}_policy_{category}"
            versioned = category in ("shipping", "returns", "warranty")
            versions = []
            if versioned:
                versions.append(make_version(doc_id, 1, policy_text(prefix, category, 1, workspace),
                                             history_start.isoformat(), (cutover - timedelta(days=1)).isoformat(),
                                             timestamp(history_start - timedelta(days=7))))
            current_version = 2 if versioned else 1
            current_content = policy_text(prefix, category, current_version, workspace)
            versions.append(make_version(doc_id, current_version, current_content,
                                         cutover.isoformat() if versioned else history_start.isoformat(), None,
                                         timestamp(cutover - timedelta(days=7)) if versioned else timestamp(history_start - timedelta(days=7))))
            docs.append({"id": doc_id, "workspace_id": workspace_id,
                         "title": category.replace("_", " ").title() + (" and exceptions" if category == "returns" else " policy"),
                         "kind": "pdf" if category in ("shipping", "returns", "warranty") else "markdown",
                         "category": category, "status": "published", "authority": "official_policy",
                         "current_version": current_version, "versions": versions})
        if prefix == "ns":
            extra = (
                ("returns", "Monitor arrival inspection", "Inspect a new monitor within seven days of its delivery scan. Photograph carton damage before discarding packing material. This guide explains inspection, not the return deadline; the official Returns and exceptions policy controls eligibility. Record the monitor model, serial label, and observed defect. A dark pixel report should include the screen color and location. Do not promise an automatic exchange from a photo alone."),
                ("shipping", "Split shipment guide", "A multi-line order can leave in separate cartons. Each shipment has its own tracking and delivered scan; support must match the purchased line to the correct carton before stating that an item arrived. A carrier label created event is not the same as carrier acceptance. If one carton arrives and another is still moving, explain both states and offer an operator ticket after five business days without movement."),
                ("compatibility", "Monitor arm fit worksheet", "Record the display's VESA pattern, unpacked weight without stand, intended desk material, and desktop thickness. Compare all four values with the chosen arm manual. Screen diagonal alone cannot establish compatibility. If the customer cannot provide a monitor model or measured weight, ask for it. Never infer VESA from a brand name."),
                ("assembly", "Desk cable routing", "Leave a loose service loop from the desk surface to the floor that reaches the maximum height. Keep cables outside moving columns and test travel before fastening clips. Mount power strips according to their own instructions. Do not route a cable across a sharp frame edge. A desk that stops during travel should be checked for obstruction before resetting."),
                ("care", "Fabric and felt care", "Vacuum acoustic felt with a soft brush at low suction. Spot-clean chair fabric with a lightly damp cloth and mild soap after testing a hidden area. Do not saturate felt, soak chair foam, or use bleach. Allow the material to dry before use. Document pre-existing stains when opening a service ticket."),
                ("payments", "Receipt reading guide", "A receipt shows item unit price, quantity, order reference, and total in USD. The support console displays integer cents to avoid rounding ambiguity. Staff can explain an itemized charge but cannot collect card details or process a refund through the pilot. For a disputed charge, create a redacted operator ticket and use the customer's verified order context."),
                ("troubleshooting", "Display signal checklist", "Before calling a monitor defective, confirm the panel's power LED, selected input, cable, and the computer's display detection. Test a known-good cable if available. For docks, confirm DisplayPort alternate mode on the host port. Record the exact model and result of each step. If there is smoke or electrical smell, disconnect power and stop troubleshooting."),
            )
            guide_notes = (
                "A clear operator handoff includes the promised date, carrier event timestamps, carton condition, and the customer's preferred safe contact channel. Refer the actual eligibility decision to the dated returns policy.",
                "If a carton lacks a delivered scan, avoid telling the customer that every item arrived. List which line belongs to which shipment and what carrier event is still missing.",
                "Use the manufacturer's published weight without stand where available. If only shipping weight is known, request the actual panel weight; packaging can materially change the number.",
                "At the lowest and highest desk positions, inspect each cord for strain and snagging. Any loose cable clip should be repositioned before normal use, and damaged insulation requires the device to be disconnected.",
                "For persistent marks, photograph the affected material and note the cleaning method already tried. An operator can compare that evidence with the care and warranty documents without promising coverage in advance.",
                "If the customer cannot identify the itemized charge, ask for the verified order reference and the amount shown on the receipt. Do not repeat or store card digits in the ticket.",
                "If the checks fail, include the model, cable type, LED state, host device, and input selection in the ticket. This helps an operator distinguish a panel defect from a missing video signal.",
            )
            for index, (category, title, body) in enumerate(extra, 1):
                doc_id = f"doc_ns_guide_{index:02d}"
                content = f"# {title}\n\n{body}\n\n## Support follow-up\n{guide_notes[index - 1]}\n\nRelated knowledge: {category.title()} policy; relevant product manual."
                docs.append({"id": doc_id, "workspace_id": workspace_id, "title": title,
                             "kind": "markdown", "category": category, "status": "published", "authority": "support_guide",
                             "current_version": 1, "versions": [make_version(doc_id, 1, content,
                                (reference - timedelta(days=269)).isoformat(), None,
                                timestamp(reference - timedelta(days=281)))]})
            # A current FAQ deliberately contains broad wording; the official policy takes precedence.
            doc_id = "doc_ns_faq_return_overview"
            content = "# Returns overview FAQ\n\nMost unopened items can be sent back within 30 days of delivery. This short overview omits category exceptions and should not be used to decide monitor eligibility. See the official Returns and exceptions policy for monitor deadlines, late-delivery review, condition, and quantity rules. A draft request is not a refund.\n\n## Before requesting a return\nConfirm the authenticated order, identify the specific line and quantity, and check the delivered scan. A product that has not arrived cannot enter the standard return clock. Prior recorded returns reduce the remaining quantity. If the condition is unclear, describe it to support before a request is drafted.\n\n## Which source controls?\nThis FAQ is a general explanation. The dated official returns policy controls any difference in deadlines, especially the monitor exception. An operator records the final decision for an exception request."
            docs.append({"id": doc_id, "workspace_id": workspace_id, "title": "Returns overview FAQ",
                         "kind": "markdown", "category": "returns", "status": "published", "authority": "faq",
                         "current_version": 1, "versions": [make_version(doc_id, 1, content,
                            (reference - timedelta(days=238)).isoformat(), None,
                            timestamp(reference - timedelta(days=245)))]})
            # Exactly 64 Northstar documents: 9 policies + 7 guides + 1 FAQ + 47 manuals.
            manual_count = 47
        else:
            # Exactly 16 Harbor documents: 8 policies + 8 manuals.
            manual_count = 8
        workspace_products = [product for product in products if product["workspace_id"] == workspace_id]
        for product in workspace_products[:manual_count]:
            doc_id = f"doc_{prefix}_manual_{product['sku'].lower().replace('-', '_')}"
            content = manual_text(product, workspace)
            docs.append({"id": doc_id, "workspace_id": workspace_id,
                         "title": f"{product['name']} owner manual", "kind": "pdf" if len(docs) % 3 == 0 else "markdown",
                         "category": "product_specs", "product_id": product["id"], "status": "published",
                         "authority": "product_manual", "current_version": 1,
                         "versions": [make_version(doc_id, 1, content, history_start.isoformat(), None,
                                                     timestamp(history_start - timedelta(days=7)))]})
    return docs


def build_conversations(orders: list[dict[str, Any]], products: list[dict[str, Any]], reference: date, rng: random.Random) -> list[dict[str, Any]]:
    conversations: list[dict[str, Any]] = []
    by_ws_orders = {ws: [order for order in orders if order["workspace_id"] == ws] for ws in ("ws_northstar", "ws_harbor")}
    product_by_id = {product["id"]: product for product in products}
    intents = ("delivery_update", "return_question", "product_fit", "warranty_question", "setup_help", "missing_information")
    for prefix, workspace, count in (("ns", "ws_northstar", 320), ("hb", "ws_harbor", 80)):
        order_pool = by_ws_orders[workspace]
        for number in range(1, count + 1):
            hero = prefix == "ns" and number == 1
            order = orders[0] if hero else rng.choice(order_pool)
            product = product_by_id[order["lines"][0]["product_id"]]
            intent = "return_question" if hero else intents[(number * 7) % len(intents)]
            subject = {
                "delivery_update": f"Delivery for {order['number']}",
                "return_question": f"Return request for {product['name']}",
                "product_fit": f"Fit question about {product['name']}",
                "warranty_question": f"Warranty coverage for {product['name']}",
                "setup_help": f"Setup help with {product['name']}",
                "missing_information": f"Question about {product['name']}",
            }[intent]
            conv_id = "conv_ns_demo_001" if hero else f"conv_{prefix}_{number:04d}"
            first_day = reference - timedelta(days=7) if hero else day_at(reference, rng.randint(0, min(330, max(0, (reference - date.fromisoformat(order["placed_at"][:10])).days))))
            if hero:
                messages = [
                    {"id": "msg_ns_demo_001", "role": "customer", "content": f"My {product['name']} on {order['number']} arrived after the promised date. Can I return it?", "created_at": timestamp(first_day, 9), "citations": []},
                    {"id": "msg_ns_demo_002", "role": "assistant", "content": "I can see the delivered scan was 12 days later than promised. The normal monitor window has ended, but your request may qualify for the late-delivery exception. I can draft it for operator review; no refund is issued now.", "created_at": timestamp(first_day, 9), "citations": ["doc_ns_policy_returns_v2", "doc_ns_policy_shipping_v2"]},
                ]
            else:
                question = {
                    "delivery_update": f"Could you check the latest status of order {order['number']}? The carrier page is unclear.",
                    "return_question": f"How does the return window apply to the {product['name']} on {order['number']}?",
                    "product_fit": f"Will the {product['name']} fit my setup? I can send measurements if needed.",
                    "warranty_question": f"What coverage applies to a fault with my {product['name']}?",
                    "setup_help": f"I am setting up the {product['name']} and need the key specifications.",
                    "missing_information": f"Can you confirm whether the {product['name']} works with my older laptop? I do not know the laptop model.",
                }[intent]
                answer = {
                    "delivery_update": "I can check the shipment attached to your authenticated order. If its carrier scan is stale for five business days, I can prepare an operator ticket.",
                    "return_question": "I will compare the delivery scan, item category, condition, quantity, and previous returns before drafting a request.",
                    "product_fit": "Please share the relevant measurements or device model so I can compare them with the manual instead of guessing.",
                    "warranty_question": "Coverage depends on the category, delivery date, and cause of the fault. Please describe the symptom and any troubleshooting tried.",
                    "setup_help": "The owner manual has the model-specific setup sequence and dimensions. Which step is causing trouble?",
                    "missing_information": "I cannot confirm compatibility without the laptop model and its USB-C video specification. Please share those details.",
                }[intent]
                messages = [
                    {"id": f"msg_{prefix}_{number:04d}_1", "role": "customer", "content": question, "created_at": timestamp(first_day, 9), "citations": []},
                    {"id": f"msg_{prefix}_{number:04d}_2", "role": "assistant", "content": answer, "created_at": timestamp(first_day, 9), "citations": []},
                ]
                if number % 4 == 0:
                    messages.extend([
                        {"id": f"msg_{prefix}_{number:04d}_3", "role": "customer", "content": "Thanks. I can provide that detail. What should I send first?", "created_at": timestamp(first_day, 10), "citations": []},
                        {"id": f"msg_{prefix}_{number:04d}_4", "role": "operator", "content": "Please send the model label or measurement and a photo that does not show payment information.", "created_at": timestamp(first_day, 10), "citations": []},
                    ])
            conversations.append({"id": conv_id, "workspace_id": workspace, "customer_id": order["customer_id"],
                                  "subject": subject, "status": "open" if hero else ("resolved" if number % 5 else "pending"),
                                  "updated_at": messages[-1]["created_at"], "order_id": order["id"], "messages": messages})
    return conversations


def build_proposals(orders: list[dict[str, Any]], conversations: list[dict[str, Any]],
                    products: list[dict[str, Any]], workspaces: list[dict[str, Any]], reference: date,
                    rng: random.Random) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    conv_by_order = {conv["order_id"]: conv["id"] for conv in conversations}
    product_category = {product["id"]: product["category"] for product in products}
    return_policy = {workspace["id"]: workspace["return_policy"] for workspace in workspaces}
    for prefix, workspace, count in (("ns", "ws_northstar", 32), ("hb", "ws_harbor", 8)):
        eligible_pool = [order for order in orders if order["workspace_id"] == workspace and order["status"] == "delivered"
                         and order["id"] != "ord_ns_demo_001" and (reference - date.fromisoformat(order["shipments"][0]["delivered_at"][:10])).days <= 45
                         and order["lines"][0]["returned_quantity"] < order["lines"][0]["quantity"]]
        rng.shuffle(eligible_pool)
        for number in range(1, count + 1):
            hero = prefix == "ns" and number == 1
            status = "pending_review" if hero else ("pending_review", "approved", "rejected", "expired", "executed")[(number - 1) % 5]
            if hero:
                order = orders[0]
            elif prefix == "hb" and number == 1:
                # This seeded review is exercised by the concurrency journey.
                # Keep its accessory order inside Harbor's configured return window.
                recent_accessories = [candidate for candidate in eligible_pool
                    if product_category[candidate["lines"][0]["product_id"]] == "accessory"
                    and (reference - date.fromisoformat(
                        candidate["shipments"][0]["delivered_at"][:10])).days <=
                        int(return_policy[workspace]["standard_days"])]
                if not recent_accessories:
                    raise ValueError("No eligible Harbor accessory order for seeded review")
                order = recent_accessories[0]
                eligible_pool.remove(order)
            elif status == "expired":
                aged = [candidate for candidate in eligible_pool if (reference - date.fromisoformat(candidate["shipments"][0]["delivered_at"][:10])).days >= 12]
                if not aged:
                    raise ValueError("Not enough delivered orders for expired proposals")
                order = aged.pop()
                eligible_pool.remove(order)
            else:
                order = eligible_pool.pop()
            line = order["lines"][0]
            delivery = date.fromisoformat(order["shipments"][0]["delivered_at"][:10])
            created = reference - timedelta(days=1) if hero else (
                max(delivery, reference - timedelta(days=rng.randint(12, 19))) if status == "expired"
                else max(delivery, reference - timedelta(days=rng.randint(1, 19)))
            )
            requires_review = hero or status != "executed" or number % 3 == 0
            proposal = {
                "id": "proposal_ns_demo_001" if hero else f"proposal_{prefix}_{number:03d}",
                "workspace_id": workspace, "customer_id": order["customer_id"],
                "conversation_id": "conv_ns_demo_001" if hero else conv_by_order.get(order["id"]),
                "order_id": order["id"], "line_id": line["id"], "quantity": 1,
                "condition": "unopened" if hero else ("unopened", "opened", "unknown", "damaged")[(number - 1) % 4],
                "reason": "late_delivery" if hero else ("changed_mind", "wrong_fit", "damaged", "late_delivery")[(number - 1) % 4],
                "policy_result": "late_delivery_exception" if hero else ("eligible", "review_required", "ineligible")[(number - 1) % 3],
                "status": status, "requires_review": requires_review,
                "version": 1 if status in ("pending_review", "expired") else 2,
                "expires_at": timestamp(reference + timedelta(days=7), 23) if status == "pending_review" else timestamp(created + timedelta(days=7), 23),
                "created_at": timestamp(created, 11),
                "reviewed_at": timestamp(min(reference, created + timedelta(days=1)), 11) if status in ("approved", "rejected", "executed") else None,
                "reviewer_id": f"user_{prefix}_operator" if status in ("approved", "rejected", "executed") else None,
            }
            if status == "executed":
                line["returned_quantity"] += 1
                order["returns"].append({"id": f"return_from_{proposal['id']}", "line_id": line["id"],
                                         "quantity": 1, "status": "recorded", "created_at": proposal["reviewed_at"],
                                         "reason": proposal["reason"], "proposal_id": proposal["id"]})
            proposals.append(proposal)
    return proposals


def build_small(full: dict[str, Any]) -> dict[str, Any]:
    """Keep the hero journey and a few complete records from each workspace."""
    conversations = [c for c in full["conversations"] if c["workspace_id"] == "ws_northstar"][:8]
    conversations += [c for c in full["conversations"] if c["workspace_id"] == "ws_harbor"][:4]
    proposals = [p for p in full["proposals"] if p["workspace_id"] == "ws_northstar"][:3]
    proposals += [p for p in full["proposals"] if p["workspace_id"] == "ws_harbor"][:1]
    conversation_ids = {c["id"] for c in conversations}
    linked_conversation_ids = {p["conversation_id"] for p in proposals if p["conversation_id"]}
    conversations += [c for c in full["conversations"] if c["id"] in linked_conversation_ids - conversation_ids]
    order_ids = {c["order_id"] for c in conversations} | {p["order_id"] for p in proposals}
    order_ids |= {o["id"] for o in [o for o in full["orders"] if o["workspace_id"] == "ws_northstar"][:20]}
    order_ids |= {o["id"] for o in [o for o in full["orders"] if o["workspace_id"] == "ws_harbor"][:10]}
    orders = [o for o in full["orders"] if o["id"] in order_ids]
    product_ids = {line["product_id"] for order in orders for line in order["lines"]}
    customer_ids = {order["customer_id"] for order in orders}
    products = [p for p in full["products"] if p["id"] in product_ids]
    customers = [c for c in full["customers"] if c["id"] in customer_ids]
    policy_ids = {"doc_ns_policy_returns", "doc_ns_policy_shipping", "doc_ns_policy_accounts",
                  "doc_ns_policy_compatibility", "doc_hb_policy_returns", "doc_hb_policy_accounts"}
    documents = [d for d in full["documents"] if d["id"] in policy_ids]
    documents += [d for d in full["documents"] if d.get("product_id") in product_ids and d["workspace_id"] == "ws_northstar"][:8]
    documents += [d for d in full["documents"] if d.get("product_id") in product_ids and d["workspace_id"] == "ws_harbor"][:4]
    return {"metadata": {**full["metadata"], "size": "small", "source": "deterministic subset of full fixture"},
            "workspaces": full["workspaces"], "users": [u for u in full["users"] if u["customer_id"] is None or u["customer_id"] in customer_ids],
            "customers": customers, "products": products, "orders": orders, "documents": documents,
            "conversations": conversations, "proposals": proposals}


def validate(data: dict[str, Any], full: bool) -> dict[str, Any]:
    expected = {"workspaces": 2, "products": 120, "customers": 800, "orders": 3000,
                "documents": 80, "conversations": 400, "proposals": 40}
    counts = {name: len(data[name]) for name in expected}
    if full and counts != expected:
        raise ValueError(f"Wrong counts: {counts} != {expected}")
    ids = {name: {row["id"] for row in data[name]} for name in expected}
    for name in expected:
        if len(ids[name]) != counts[name]:
            raise ValueError(f"Duplicate {name} ID")
    product_ws = {p["id"]: p["workspace_id"] for p in data["products"]}
    customer_ws = {c["id"]: c["workspace_id"] for c in data["customers"]}
    order_ws = {o["id"]: o["workspace_id"] for o in data["orders"]}
    conversation_ws = {c["id"]: c["workspace_id"] for c in data["conversations"]}
    line_by_id = {}
    for user in data["users"]:
        if user["workspace_id"] not in ids["workspaces"] or (user["customer_id"] and customer_ws[user["customer_id"]] != user["workspace_id"]):
            raise ValueError(f"Invalid user scope: {user['id']}")
    for order in data["orders"]:
        if customer_ws[order["customer_id"]] != order["workspace_id"]:
            raise ValueError(f"Invalid order/customer scope: {order['id']}")
        total = 0
        for line in order["lines"]:
            if product_ws[line["product_id"]] != order["workspace_id"]:
                raise ValueError(f"Invalid order/product scope: {order['id']}")
            if not 0 <= line["returned_quantity"] <= line["quantity"]:
                raise ValueError(f"Invalid returned quantity: {line['id']}")
            total += line["unit_price_cents"] * line["quantity"]
            line_by_id[line["id"]] = (order["id"], order["workspace_id"])
        if total != order["total_cents"]:
            raise ValueError(f"Incorrect total: {order['id']}")
        for shipment in order["shipments"]:
            if shipment["delivered_at"] and (not shipment["shipped_at"] or shipment["delivered_at"] < shipment["shipped_at"]):
                raise ValueError(f"Impossible shipment timeline: {order['id']}")
        for return_record in order["returns"]:
            if line_by_id[return_record["line_id"]][0] != order["id"]:
                raise ValueError(f"Invalid return line: {order['id']}")
    for document in data["documents"]:
        if document["workspace_id"] not in ids["workspaces"]:
            raise ValueError(f"Invalid document scope: {document['id']}")
        for version in document["versions"]:
            if version["sha256"] != content_hash(version["content"]):
                raise ValueError(f"Invalid document hash: {document['id']}")
    for conversation in data["conversations"]:
        if customer_ws[conversation["customer_id"]] != conversation["workspace_id"]:
            raise ValueError(f"Invalid conversation/customer scope: {conversation['id']}")
        if conversation["order_id"] not in order_ws or order_ws[conversation["order_id"]] != conversation["workspace_id"]:
            raise ValueError(f"Invalid conversation/order scope: {conversation['id']}")
    for proposal in data["proposals"]:
        ws = proposal["workspace_id"]
        if customer_ws[proposal["customer_id"]] != ws or order_ws[proposal["order_id"]] != ws:
            raise ValueError(f"Invalid proposal scope: {proposal['id']}")
        if line_by_id[proposal["line_id"]] != (proposal["order_id"], ws):
            raise ValueError(f"Invalid proposal line: {proposal['id']}")
        if proposal["conversation_id"] and conversation_ws[proposal["conversation_id"]] != ws:
            raise ValueError(f"Invalid proposal conversation: {proposal['id']}")
    if full:
        categories = {document["category"] for document in data["documents"]}
        if len(categories) < 8:
            raise ValueError("Too few document categories")
        months = {order["placed_at"][:7] for order in data["orders"]}
        if len(months) != 12:
            raise ValueError(f"Orders span {len(months)} months, expected 12")
    return {"counts": counts, "workspace_counts": {
        workspace: {name: sum(item["workspace_id"] == workspace for item in data[name]) for name in ("products", "customers", "orders", "documents", "conversations", "proposals")}
        for workspace in ids["workspaces"]},
        "document_categories": dict(Counter(document["category"] for document in data["documents"])),
        "order_months": dict(sorted(Counter(order["placed_at"][:7] for order in data["orders"]).items()))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--reference-date", type=date.fromisoformat, default=DEFAULT_REFERENCE_DATE)
    parser.add_argument("--output", type=Path, default=ROOT / "fixtures" / "demo_full.json")
    parser.add_argument("--small-output", type=Path, default=ROOT / "fixtures" / "demo_small.json")
    args = parser.parse_args()
    rng = random.Random(args.seed)
    workspaces = build_workspaces(args.reference_date)
    products = build_products()
    customers = build_customers()
    users = build_users(customers)
    orders = build_orders(products, customers, args.reference_date, rng)
    documents = build_documents(products, workspaces)
    conversations = build_conversations(orders, products, args.reference_date, rng)
    proposals = build_proposals(orders, conversations, products, workspaces, args.reference_date, rng)
    full = {"metadata": {"label": "Synthetic demo dataset", "size": "full", "seed": args.seed,
                         "reference_date": args.reference_date.isoformat(), "schema_version": 1},
            "workspaces": workspaces, "users": users, "customers": customers, "products": products,
            "orders": orders, "documents": documents, "conversations": conversations, "proposals": proposals}
    full_summary = validate(full, full=True)
    small = build_small(full)
    small_summary = validate(small, full=False)
    for path, data in ((args.output, full), (args.small_output, small)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"full": full_summary, "small": small_summary,
                      "full_path": str(args.output), "small_path": str(args.small_output)}, indent=2))


if __name__ == "__main__":
    main()
