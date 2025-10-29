import fitz  # PyMuPDF
from PIL import Image, ImageDraw
import os

def pad_rect(rect_pdf, pad):
    x0, y0, x1, y1 = rect_pdf
    return (x0 - pad, y0 - pad, x1 + pad, y1 + pad)

####################################################
# 1. Merging logic for drawing rectangles
####################################################

def merge_rects(rects, proximity_tol=2, max_vertical_gap=20):
    """
    Merge rectangles if they overlap / are close, AND their vertical centers
    are not too far apart. This stops chain-merging across the whole page.
    rects are in PDF coords: (x0,y0,x1,y1).
    """

    merged = []

    def overlap_or_close(a, b):
        ax0, ay0, ax1, ay1 = a
        bx0, by0, bx1, by1 = b

        # Expand A by a tolerance
        ax0e = ax0 - proximity_tol
        ay0e = ay0 - proximity_tol
        ax1e = ax1 + proximity_tol
        ay1e = ay1 + proximity_tol

        # Overlap check
        overlap_x = not (ax1e < bx0 or bx1 < ax0e)
        overlap_y = not (ay1e < by0 or by1 < ay0e)
        if not (overlap_x and overlap_y):
            return False

        # Additional guard: don't merge if centers are too far apart vertically
        ayc = (ay0 + ay1) / 2
        byc = (by0 + by1) / 2
        if abs(ayc - byc) > max_vertical_gap:
            return False

        return True

    rects = rects[:]
    changed = True
    while changed:
        changed = False
        new_rects = []

        while rects:
            base = rects.pop()
            bx0, by0, bx1, by1 = base
            absorbed = []

            for i, other in enumerate(rects):
                if overlap_or_close(base, other):
                    ox0, oy0, ox1, oy1 = other
                    # Union
                    bx0 = min(bx0, ox0)
                    by0 = min(by0, oy0)
                    bx1 = max(bx1, ox1)
                    by1 = max(by1, oy1)
                    absorbed.append(i)
                    changed = True

            # Drop 'absorbed' already merged
            for idx in sorted(absorbed, reverse=True):
                rects.pop(idx)

            new_rects.append((bx0, by0, bx1, by1))

        rects = new_rects[:]

    merged.extend(rects)
    return merged


####################################################
# 2. Helper to render coordinate grid overlay
####################################################

def make_coordinate_grid_image(
    base_pix,
    page_w_pdf,
    page_h_pdf,
    zoom,
    save_path,
    step_pdf=50,
    label_font_color=(0, 0, 0),
    grid_color=(180, 180, 255)
):
    """
    Create a calibration / reference image:
    - background: page raster (pix)
    - grid lines every `step_pdf` PDF units
    - each grid line labeled in PDF coords (x or y)

    We assume: pixel_x = pdf_x * zoom, pixel_y = pdf_y * zoom
               (which is the same transform we use for boxes)
    """
    img = Image.frombytes("RGB", [base_pix.width, base_pix.height], base_pix.samples)
    draw = ImageDraw.Draw(img)

    # Vertical grid lines (x = const in PDF coords)
    x_pdf = 0
    while x_pdf <= page_w_pdf:
        x_px = x_pdf * zoom
        draw.line([(x_px, 0), (x_px, base_pix.height)], fill=grid_color, width=1)
        # label at top
        label = f"x={int(x_pdf)}"
        draw.text((x_px + 2, 2), label, fill=label_font_color)
        x_pdf += step_pdf

    # Horizontal grid lines (y = const in PDF coords)
    y_pdf = 0
    while y_pdf <= page_h_pdf:
        y_px = y_pdf * zoom
        draw.line([(0, y_px), (base_pix.width, y_px)], fill=grid_color, width=1)
        # label at left
        label = f"y={int(y_pdf)}"
        draw.text((2, y_px + 2), label, fill=label_font_color)
        y_pdf += step_pdf

    img.save(save_path)
    print("Saved COORD GRID image:", save_path)


####################################################
# 3. Main visualizer
####################################################

def visualize_layout_debug(
    page,
    page_num,
    dpi=150,
    save_dir="Projects/exam_paper_parser_V1.0/data/raw_papers/pdf_layout",
    show_labels=True
):
    """
    Produces three debug images for a given PDF page:
      1. RAW layout: text (red), images (green), raw drawing prims (blue thin)
      2. MERGED layout: text (red), images (green), merged clusters (blue thick)
      3. COORD GRID layout: page raster + PDF coordinate grid labels

    Also prints:
      TEXT BLOCKS (red)
      IMAGE BLOCKS (green)
      DRAWING PRIMITIVES (blue RAW)
      FINAL drawing_clusters (blue MERGED)
    """

    os.makedirs(save_dir, exist_ok=True)

    # -----------------
    # Open and render
    # -----------------
    # doc = fitz.open(pdf_path)
    # page = doc[page_num]

    page_rect = page.rect
    page_w_pdf = float(page_rect.x1 - page_rect.x0)
    page_h_pdf = float(page_rect.y1 - page_rect.y0)
    page_area_pdf = page_w_pdf * page_h_pdf if page_w_pdf and page_h_pdf else 1.0

    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)

    raw_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    merged_img = raw_img.copy()

    raw_draw = ImageDraw.Draw(raw_img)
    merged_draw = ImageDraw.Draw(merged_img)

    # Coordinate transform for boxes:
    # On your PDF we discovered just scaling is enough (no Y-flip).
    def bbox_pdf_to_img_scaled(bbox_pdf):
        x0, y0, x1, y1 = bbox_pdf
        sx0, sy0 = x0 * zoom, y0 * zoom
        sx1, sy1 = x1 * zoom, y1 * zoom
        left, right = sx0, sx1
        top, bottom = sy0, sy1
        if top > bottom:
            top, bottom = bottom, top
        return (left, top, right, bottom)

    # -----------------
    # 1. Extract text/image blocks
    # -----------------
    text_blocks = []
    image_blocks = []

    page_dict = page.get_text("dict")
    for b_idx, block in enumerate(page_dict["blocks"]):
        bbox_pdf = tuple(block["bbox"])
        btype = block.get("type", 0)

        # collect any text spans
        spans_text = []
        if "lines" in block:
            for line in block["lines"]:
                for span in line["spans"]:
                    spans_text.append(span["text"])
        joined_text = " ".join(spans_text).strip()

        if btype == 0:
            text_blocks.append({
                "id": f"T{b_idx}",
                "bbox_pdf": bbox_pdf,
                "text": joined_text,
            })
        elif btype == 1:
            image_blocks.append({
                "id": f"I{b_idx}",
                "bbox_pdf": bbox_pdf,
                "text": joined_text,
            })
        else:
            pass

    # -----------------
    # 2. Extract raw drawing primitives
    # -----------------
    drawings_raw = page.get_drawings()
    drawing_primitives = []
    for d_idx, d in enumerate(drawings_raw):
        rect = fitz.Rect(d["rect"])
        bbox_pdf = (float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1))
        drawing_primitives.append({
            "id": f"DRAW_RAW{d_idx}",
            "bbox_pdf": bbox_pdf,
            "color": d.get("color"),
            "fill": d.get("fill"),
        })

    # -----------------
    # 3. Filter drawing primitives BEFORE merging
    # -----------------
    # We'll keep graph-like stuff while trying to remove footer bars + full-page frame.
    upper_half_limit = page_h_pdf * 0.6  # guess that figure is in top ~60%

    fig_band_ymins = []
    fig_band_ymaxs = []
    for prim in drawing_primitives:
        x0, y0, x1, y1 = prim["bbox_pdf"]
        # consider shapes that extend above the threshold
        if y1 > upper_half_limit:
            fig_band_ymins.append(y0)
            fig_band_ymaxs.append(y1)

    if fig_band_ymins and fig_band_ymaxs:
        fig_band_min_y = min(fig_band_ymins)
        fig_band_max_y = max(fig_band_ymaxs)
    else:
        fig_band_min_y = 0
        fig_band_max_y = page_h_pdf

    filtered_rects_pdf = []

    for prim in drawing_primitives:
        x0, y0, x1, y1 = prim["bbox_pdf"]
        w = x1 - x0
        h = y1 - y0
        if w <= 0 or h <= 0:
            continue

        w_ratio = w / page_w_pdf if page_w_pdf else 0
        h_ratio = h / page_h_pdf if page_h_pdf else 0

        # RULE A: drop almost-whole-page frames
        if (w_ratio > 0.9 and h_ratio > 0.9):
            continue

        # RULE B: drop very-wide bottom footer lines (barcode area)
        if y0 < 50 and w_ratio > 0.5:
            continue

        # RULE C: drop super-long skinny horizontals only if BELOW the main figure band
        long_and_skinny = (w_ratio > 0.6 and h < 3)
        below_band = (y1 < (fig_band_min_y - 60))  # more forgiving
        if long_and_skinny and below_band:
            continue


        filtered_rects_pdf.append(prim["bbox_pdf"])

    # -----------------
    # 4. Merge filtered rectangles into clusters and post-filter
    # -----------------
    merged_rects_pdf = merge_rects(
        filtered_rects_pdf,
        proximity_tol=2,
        max_vertical_gap=20
    )

    drawing_clusters = []
    cluster_idx = 0

    for rect_pdf in merged_rects_pdf:
        x0, y0, x1, y1 = rect_pdf
        w = x1 - x0
        h = y1 - y0
        area = w * h
        if area <= 0:
            print("[drop cluster] zero/nonpositive area", rect_pdf)
            continue

        w_ratio = w / page_w_pdf
        h_ratio = h / page_h_pdf
        cover_ratio = area / page_area_pdf

        drop = False
        drop_reason = None

        # (1) Very big "page frame / page pane" style cluster
        # drop if it covers most of the page in BOTH width and height
        if (w_ratio > 0.7 and h_ratio > 0.7):
            drop = True
            drop_reason = "looks like large page region (big in both w & h)"



        # (2) Very tiny noise
        if area < 1000:
            drop = True
            drop_reason = "too small / noise"

        if drop:
            print("[drop cluster]", rect_pdf,
                  "reason:", drop_reason,
                  f"(w_ratio={w_ratio:.2f}, h_ratio={h_ratio:.2f}, area={area:.1f})")
            continue

        PADDING_PDF = 5  # tune if you want a tighter/looser fit

        padded_rect = pad_rect(rect_pdf, PADDING_PDF)

        drawing_clusters.append({
            "id": f"D{cluster_idx}",
            "bbox_pdf": padded_rect,
            "w_ratio": w_ratio,
            "h_ratio": h_ratio,
            "area": area,
            "y_range": (y0, y1),
        })
    
        cluster_idx += 1

    print("FINAL drawing_clusters:")
    for dc in drawing_clusters:
        print(" ", dc["id"], dc["bbox_pdf"],
              f"(w_ratio={dc['w_ratio']:.2f}, h_ratio={dc['h_ratio']:.2f}, area={dc['area']:.1f})")

    # -----------------
    # 5. Draw RAW layout
    # -----------------
    for tb in text_blocks:
        box_img = bbox_pdf_to_img_scaled(tb["bbox_pdf"])
        raw_draw.rectangle(box_img, outline="red", width=2)
        if show_labels:
            lx, ly = box_img[0], box_img[1]
            raw_draw.rectangle([lx, ly, lx+80, ly+16], fill="white", outline="red", width=1)
            raw_draw.text((lx+3, ly+2), tb["id"], fill="red")

    for ib in image_blocks:
        box_img = bbox_pdf_to_img_scaled(ib["bbox_pdf"])
        raw_draw.rectangle(box_img, outline="green", width=2)
        if show_labels:
            lx, ly = box_img[0], box_img[1]
            raw_draw.rectangle([lx, ly, lx+80, ly+16], fill="white", outline="green", width=1)
            raw_draw.text((lx+3, ly+2), ib["id"], fill="green")

    for dp in drawing_primitives:
        box_img = bbox_pdf_to_img_scaled(dp["bbox_pdf"])
        raw_draw.rectangle(box_img, outline="blue", width=1)
        if show_labels:
            lx, ly = box_img[0], box_img[1]
            label = dp["id"]
            raw_draw.rectangle([lx, ly, lx+110, ly+14], fill="white", outline="blue", width=1)
            raw_draw.text((lx+3, ly+1), label, fill="blue")

    raw_path = os.path.join(
        save_dir,
        f"page_{page_num}_raw_layout.png"
    )
    raw_img.save(raw_path)
    print("Saved RAW layout image:", raw_path)

    # -----------------
    # 6. Draw MERGED layout
    # -----------------
    for tb in text_blocks:
        box_img = bbox_pdf_to_img_scaled(tb["bbox_pdf"])
        merged_draw.rectangle(box_img, outline="red", width=2)
        if show_labels:
            lx, ly = box_img[0], box_img[1]
            merged_draw.rectangle([lx, ly, lx+80, ly+16], fill="white", outline="red", width=1)
            merged_draw.text((lx+3, ly+2), tb["id"], fill="red")

    for ib in image_blocks:
        box_img = bbox_pdf_to_img_scaled(ib["bbox_pdf"])
        merged_draw.rectangle(box_img, outline="green", width=2)
        if show_labels:
            lx, ly = box_img[0], box_img[1]
            merged_draw.rectangle([lx, ly, lx+80, ly+16], fill="white", outline="green", width=1)
            merged_draw.text((lx+3, ly+2), ib["id"], fill="green")

    for dc in drawing_clusters:
        box_img = bbox_pdf_to_img_scaled(dc["bbox_pdf"])
        merged_draw.rectangle(box_img, outline="blue", width=3)
        if show_labels:
            lx, ly = box_img[0], box_img[1]
            merged_draw.rectangle([lx, ly, lx+60, ly+16], fill="white", outline="blue", width=1)
            merged_draw.text((lx+3, ly+2), dc["id"], fill="blue")

    merged_path = os.path.join(
        save_dir,
        f"page_{page_num}_merged_layout.png"
    )
    merged_img.save(merged_path)
    print("Saved MERGED layout image:", merged_path)

    # -----------------
    # 7. Draw COORD GRID layout
    # -----------------
    coord_grid_path = os.path.join(
        save_dir,
        f"page_{page_num}_coord_grid.png"
    )
    make_coordinate_grid_image(
        base_pix=pix,
        page_w_pdf=page_w_pdf,
        page_h_pdf=page_h_pdf,
        zoom=zoom,
        save_path=coord_grid_path,
        step_pdf=50,  # you can adjust granularity here
        label_font_color=(0, 0, 0),
        grid_color=(180, 180, 255)
    )

    # -----------------
    # 8. Console debug info
    # -----------------
    print("\n=== TEXT BLOCKS (red) ===")
    for tb in text_blocks:
        print(tb["id"])
        print(" pdf bbox:", tb["bbox_pdf"])
        print(" text:", tb["text"][:200].replace("\n", " "))
        print()

    print("=== IMAGE BLOCKS (green) ===")
    for ib in image_blocks:
        print(ib["id"])
        print(" pdf bbox:", ib["bbox_pdf"])
        print(" note (usually empty):", ib["text"][:80])
        print()

    print("=== DRAWING PRIMITIVES (blue RAW) ===")
    for dp in drawing_primitives:
        print(dp["id"])
        print(" pdf bbox:", dp["bbox_pdf"])
        print(" color:", dp["color"], " fill:", dp["fill"])
        print()

    print("=== FINAL DRAWING CLUSTERS (blue MERGED) ===")
    for dc in drawing_clusters:
        print(dc["id"])
        print(" pdf bbox:", dc["bbox_pdf"])
        print()

    

    return {
        "text_blocks": text_blocks,
        "image_blocks": image_blocks,
        "drawing_primitives": drawing_primitives,
        "drawing_clusters": drawing_clusters,
        "raw_image_path": raw_path,
        "merged_image_path": merged_path,
        "coord_grid_path": coord_grid_path
    }


####################################################
# 4. Example usage
####################################################

if __name__ == "__main__":
    pdf_path = "data/raw_papers/June 2018 QP - Paper 1 (H) Edexcel Physics GCSE.pdf"
    page_num = 2  # sonar graph page in your screenshots
    save_dir_tmp = "data/raw_papers/pdf_layout"
    doc = fitz.open(pdf_path)
    current_page = 0
    for page in doc:
    # page = doc[page_num]
        visualize_layout_debug(
            page,
            current_page,
            dpi=150,
            save_dir=save_dir_tmp,
            show_labels=True
        )
        current_page +=1
    doc.close()
