"""Render the repository architecture as editable SVG and PNG without external services."""
from html import escape
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs"
OUT.mkdir(exist_ok=True)
W, H = 1400, 1000
image = Image.new("RGB", (W, H), "#f3f6fb")
draw = ImageDraw.Draw(image)
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title desc">',
       '<title id="title">Serverless image processing architecture</title>',
       '<desc id="desc">IAM authenticated uploads to S3, SQS dispatch to a Standard Step Functions workflow, a Pillow Lambda layer, metadata in DynamoDB, notifications through SNS, and private S3 delivery through CloudFront.</desc>',
       '<rect width="1400" height="1000" fill="#f3f6fb"/>']


def font(size, bold=False):
    name = "segoeuib.ttf" if bold else "segoeui.ttf"
    try:
        return ImageFont.truetype("C:/Windows/Fonts/" + name, size)
    except OSError:
        return ImageFont.load_default(size=size)


def text(x, y, value, size=18, fill="#18273d", bold=False, center=False):
    selected = font(size, bold)
    if center:
        box = draw.textbbox((0, 0), value, font=selected)
        px = x - (box[2] - box[0]) / 2
    else:
        px = x
    draw.text((px, y), value, font=selected, fill=fill)
    weight = "700" if bold else "400"
    anchor = "middle" if center else "start"
    svg.append(f'<text x="{x}" y="{y + size}" font-family="Segoe UI,Arial,sans-serif" font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{escape(value)}</text>')


def node(bounds, title, subtitle, color="#335eea"):
    x1, y1, x2, y2 = bounds
    draw.rounded_rectangle(bounds, radius=14, fill="white", outline=color, width=2)
    draw.rounded_rectangle((x1, y1, x1+7, y2), radius=3, fill=color)
    svg.append(f'<rect x="{x1}" y="{y1}" width="{x2-x1}" height="{y2-y1}" rx="14" fill="white" stroke="{color}" stroke-width="2"/>')
    svg.append(f'<rect x="{x1}" y="{y1+12}" width="6" height="{y2-y1-24}" fill="{color}"/>')
    text((x1+x2)/2, y1+18, title, 20, bold=True, center=True)
    for index, line in enumerate(subtitle):
        text((x1+x2)/2, y1+49+index*23, line, 16, fill="#4c5c73", center=True)


def arrow(points, label=None, label_xy=None, dashed=False):
    color = "#61748e"
    draw.line(points, fill=color, width=3)
    x, y = points[-1]
    px, py = points[-2]
    if x > px:
        tip = [(x,y),(x-10,y-6),(x-10,y+6)]
    elif x < px:
        tip = [(x,y),(x+10,y-6),(x+10,y+6)]
    elif y > py:
        tip = [(x,y),(x-6,y-10),(x+6,y-10)]
    else:
        tip = [(x,y),(x-6,y+10),(x+6,y+10)]
    draw.polygon(tip, fill=color)
    dash = ' stroke-dasharray="7 5"' if dashed else ''
    coords = " ".join(f"{x},{y}" for x,y in points)
    svg.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="3"{dash}/>')
    svg.append('<polygon points="' + " ".join(f"{x},{y}" for x,y in tip) + f'" fill="{color}"/>')
    if label:
        text(*label_xy, label, 15, fill="#425570")


text(45, 25, "Serverless Image Processing Pipeline", 34, bold=True)
text(45, 73, "AWS Solutions Architect - Associate | Serverless Image Processing", 20, fill="#4c5c73")
node((40,140,200,240), "Learner", ["IAM-signed client"], "#61748e")
node((270,140,490,240), "API Gateway", ["HTTP API / AWS_IAM", "Upload + job status"], "#8b4cc2")
node((560,140,800,240), "API Lambda", ["5-minute upload form", "Unique upload key"], "#d57a13")
node((1040,140,1320,240), "Source S3 bucket", ["Private / uploads/*", "7-day demo retention"], "#368455")
arrow([(200,190),(270,190)])
arrow([(490,190),(560,190)])
arrow([(120,240),(120,285),(1180,285),(1180,240)], "Direct upload using signed POST form", (500,260), True)
arrow([(1180,285),(1180,360)], "ObjectCreated", (1200,315))
node((1040,360,1320,460), "SQS queue", ["180s visibility", "5 receives before DLQ"], "#b54278")
node((720,360,960,460), "Dispatch Lambda", ["Start named execution", "Partial batch failures"], "#d57a13")
node((260,350,620,470), "Step Functions / Standard", ["Validate > Resize > Watermark > Store", "Catch failures > record FAILED"], "#b54278")
arrow([(1040,405),(960,405)])
arrow([(720,405),(620,405)])
node((1040,540,1320,630), "Dead-letter queue", ["Dispatch failures / 14 days"], "#b54278")
arrow([(1180,460),(1180,540)])
node((260,560,620,670), "Image worker Lambda", ["Pillow / 1024px + 256px", "Image bytes stay in S3"], "#d57a13")
node((40,570,200,660), "Pillow layer", ["Linux / Python 3.12"], "#d57a13")
arrow([(440,470),(440,560)], "Task invocation", (455,505))
arrow([(200,615),(260,615)], dashed=True)
node((720,560,970,670), "Destination S3", ["staging/*: 1 day", "processed/*: 7 days"], "#368455")
arrow([(620,615),(720,615)])
node((1040,690,1320,760), "CloudWatch Logs", [], "#8b4cc2")
text(1180, 735, "All Lambda functions / 3 days", 15, center=True, fill="#4c5c73")
node((40,800,330,900), "DynamoDB", ["Dimensions / status / URLs", "1 RCU + 1 WCU / TTL 14 days"], "#335eea")
node((400,800,650,900), "SNS topic", ["Completion / failure events", "No subscribers configured"], "#b54278")
node((720,800,970,900), "CloudFront", ["HTTPS / Origin Access Control", "Reads processed/* only"], "#8b4cc2")
node((1100,800,1320,900), "Image viewers", ["Processed images only"], "#61748e")
arrow([(350,670),(350,745),(185,745),(185,800)])
arrow([(525,670),(525,800)])
arrow([(845,670),(845,800)], "Private origin", (860,730))
arrow([(970,850),(1100,850)])
text(45, 940, "Deployed in eu-west-3 + global CloudFront. Separate IAM roles. Pillow layer: Linux / Python 3.12.", 17)
text(45, 969, "Live upload, processing, metadata and CDN verified. API also reads DynamoDB status. Demo objects expire by lifecycle.", 15, fill="#4c5c73")
svg.append('</svg>')
(OUT / "architecture.svg").write_text("\n".join(svg), encoding="utf-8")
image.save(OUT / "architecture.png")
print("Created docs/architecture.svg and docs/architecture.png")
