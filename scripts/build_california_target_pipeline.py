"""Build a source-backed California prospect layer without inventing IP ownership.

The prospect layer is intentionally separate from the legal-rights census. A UC
licensee is a verified propagation or commercialization signal, not evidence that
the licensee owns the underlying variety. Local USPTO and CPVO records are
matched conservatively and surfaced as research evidence only.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT_PATH = DATA_DIR / "california_target_pipeline.json"
USPTO_PATH = DATA_DIR / "plant_patents.json"
CPVO_PATH = DATA_DIR / "cpvo_varieties.json"

UC_TREE = "https://research.ucdavis.edu/industry-support/plant-variety-licensing-program/tree-varieties-program/"
UC_GRAPE = "https://research.ucdavis.edu/industry-support/plant-variety-licensing-program/grape-licensing-program/"
UC_STRAWBERRY = "https://research.ucdavis.edu/industry-support/plant-variety-licensing-program/strawberry-licensing-program/licensed-nurseries/"


def lead(
    ident: str,
    company: str,
    location: str,
    crops: str,
    role: str,
    summary: str,
    source: str,
    priority: str,
    aliases: list[str] | None = None,
    website: str = "",
) -> dict[str, Any]:
    return {
        "id": ident,
        "companyName": company,
        "location": location,
        "cropFocus": crops,
        "role": role,
        "summary": summary,
        "sourceUrl": source,
        "priority": priority,
        "aliases": aliases or [company],
        "website": website,
        "patentReviewStatus": "pending_external_lookup",
    }


# Every profile below is supported by an official company site or a current UC
# license list. The summary avoids treating a license to propagate a variety as
# ownership of that variety.
LEADS = [
    lead("CA-001", "California Blueberry Nursery", "Selma, CA", "Blueberry", "Breeder / licensee", "Founder-led blueberry nursery with trial and commercialization activity; verify title and territory rights variety by variety.", "https://californiablueberrynursery.com/home/about-us/", "high", ["California Blueberry Nursery", "CBN"], "https://californiablueberrynursery.com/"),
    lead("CA-002", "Crown Nursery", "Red Bluff, CA", "Strawberry", "Licensed propagator", "Long-running commercial strawberry nursery and current UC strawberry licensee; value rests in propagation capability and contract durability, not presumed germplasm ownership.", UC_STRAWBERRY, "review", ["Crown Nursery", "Crown Nursery LLC"], "https://www.crownnurseryllc.com/"),
    lead("CA-003", "FlavorFirst", "Watsonville, CA", "Strawberry", "Trial / licensing platform", "Strawberry trial and licensing platform working with advanced selections and commercial propagators; assess rights-management economics and partner concentration.", "https://www.flavorfirst.com/", "review", ["FlavorFirst", "Flavor First"], "https://www.flavorfirst.com/"),
    lead("CA-004", "Lassen Canyon Nursery", "Redding, CA", "Strawberry", "Licensed propagator / breeder", "Commercial berry nursery and UC strawberry licensee with advanced-selection trial activity; confirm which selections it owns versus propagates.", UC_STRAWBERRY, "review", ["Lassen Canyon Nursery", "Lassen Canyon"], "https://www.lassencanyonnursery.com/"),
    lead("CA-005", "Cal Nursery, Inc.", "Delhi, CA", "Strawberry", "Licensed propagator", "Current UC strawberry licensee with a broad set of commercial varieties. Treat as a propagation-channel lead pending independent ownership and scale verification.", UC_STRAWBERRY, "verify", ["Cal Nursery", "CAL NURSERY, INC."], ""),
    lead("CA-006", "Innovative Organic Nursery", "Freedom, CA", "Strawberry", "Licensed propagator", "Organic strawberry nursery licensed for selected UC cultivars. Relevant as a specialty propagation and organic-market relationship lead.", UC_STRAWBERRY, "verify", ["Innovative Organic Nursery"], "https://innovativeorganicnursery.com/"),
    lead("CA-007", "Larse Farms", "Aptos, CA", "Strawberry", "Licensed grower / propagator", "UC strawberry licensee with a broad commercial variety list. Verify whether propagation is a material standalone business or internal grower capability.", UC_STRAWBERRY, "verify", ["Larse Farms"], ""),
    lead("CA-008", "Monte Vista Nursery", "McArthur, CA", "Strawberry", "Licensed propagator", "Small UC strawberry licensee with a more focused cultivar set, making it a possible regional nursery conversation.", UC_STRAWBERRY, "verify", ["Monte Vista Nursery"], ""),
    lead("CA-009", "NorCal Nursery, Inc.", "Anderson, CA", "Strawberry", "Licensed propagator", "UC strawberry licensee with broad cultivar access. Confirm ownership, customer mix, and whether it operates independently from larger berry platforms.", UC_STRAWBERRY, "verify", ["NorCal Nursery", "Norcal Nursery, Inc."], ""),
    lead("CA-010", "Sierra-Cascade Nursery, Inc.", "Susanville, CA", "Strawberry", "Licensed propagator", "UC strawberry licensee with a broad cultivar list and a northern-California operating base; possible clean-stock and propagation relationship lead.", UC_STRAWBERRY, "verify", ["Sierra-Cascade Nursery", "Sierra Cascade Nursery"], "https://www.sierracascadenursery.com/"),
    lead("CA-011", "Fresa Fortaleza", "Watsonville, CA", "Strawberry", "Master licensee", "UC strawberry master licensee for Mexico, making it an asset-light rights-management and export-channel lead rather than an assumed breeder owner.", UC_STRAWBERRY, "review", ["Fresa Fortaleza"], ""),
    lead("CA-012", "Acemi Nursery", "Kerman, CA", "Pistachio", "Licensed propagator", "UC pistachio licensee for commercial scions and pollenizers. Verify entity ownership, operating scale, and license transferability.", UC_TREE, "review", ["Acemi Nursery"], ""),
    lead("CA-013", "Green Tree Nursery", "La Grange, CA", "Almond, walnut, rootstocks", "Licensed propagator", "UC licensee across Kester almond and multiple walnut varieties/rootstocks. A broad permanent-crop nursery capability signal, not proof of underlying IP ownership.", UC_TREE, "review", ["Green Tree Nursery"], ""),
    lead("CA-014", "ProTree Nursery", "Patterson / Brentwood, CA", "Walnut, pistachio, fruit trees", "Licensed propagator", "UC licensee for pistachio and walnut material and an authorized commercial fruit-tree nursery. Confirm present operating base and customer concentration.", UC_TREE, "review", ["ProTree Nursery", "Protree Nursery, LLC"], "https://protreenursery.com/"),
    lead("CA-015", "Tudor Trees", "Yuba City, CA", "Fruit, almond, walnut, peach, prune", "Licensed propagator", "Commercial orchard-tree nursery with UC peach licensing. Relevant for a focused fruit/nut nursery profile; validate proprietary or exclusive programs.", UC_TREE, "review", ["Tudor Trees"], "https://tudortrees.com/"),
    lead("CA-016", "Sutter Buttes Nursery", "Live Oak, CA", "Walnut rootstocks", "Licensed propagator", "Commercial nursery licensed for RX1 and VX211 walnut rootstocks. A narrow, locally rooted permanent-crop propagation lead.", UC_TREE, "review", ["Sutter Buttes Nursery", "Sutter Buttes Nursery, Inc."], "https://www.sutterbuttesnursery.com/"),
    lead("CA-017", "The Nursery Company", "Chowchilla, CA", "Walnut rootstocks", "Licensed propagator", "UC licensee for VX211 walnut rootstock, associated publicly with Harris Family Enterprises. Treat as a platform/add-on lead and verify parent-company scope.", UC_TREE, "review", ["The Nursery Company"], "https://www.harrisfamilyenterprises.com/the-nursery-company"),
    lead("CA-018", "Jubilant Earth Fruit & Nut", "Yuba City, CA", "Almond, walnut, rootstocks", "Licensed propagator", "Low-profile UC licensee for Sweetheart almond, Solano walnut, RX1, and VX211. A focused diligence lead requiring basic ownership and scale work.", UC_TREE, "review", ["Jubilant Earth", "Jubilant Earth Fruit & Nut", "Jubilant Earth Fruit & Nut LLC"], ""),
    lead("CA-019", "Venice Hill Walnut Nursery", "Visalia, CA", "Walnut", "Licensed propagator", "Specialist walnut nursery and UC Wolfskill licensee. Relevant old-line orchard-nursery lead; current production and ownership need verification.", UC_TREE, "review", ["Venice Hill Walnut Nursery"], ""),
    lead("CA-020", "Cross Creek Nursery", "Visalia, CA", "Walnut", "Licensed propagator", "UC licensee for the Gillet walnut variety. Thin web footprint makes it a research lead, not a confirmed target.", UC_TREE, "verify", ["Cross Creek Nursery", "Cross Creek Nursery, Inc"], ""),
    lead("CA-021", "Tissue-Grown Corporation", "Santa Paula, CA", "Walnut, pistachio, cherry rootstocks", "Tissue culture / propagation", "Commercial tissue-culture and clean-plant propagation specialist with UC rootstock licensing. Strong technology and propagation capability; size may exceed the current target range.", UC_TREE, "review", ["Tissue-Grown Corporation", "Tissue Grown Corporation"], "https://tissuegrown.com/"),
    lead("CA-022", "L.E. Cooke Company", "Visalia, CA", "Fruit and nut trees", "Nursery / clean-stock", "Fourth-generation wholesale tree nursery with certified fruit-tree propagation capability. Confirm exclusive programs and whether its scale fits the target range.", "https://lechistory.wordpress.com/about/", "review", ["L.E. Cooke", "LE Cooke", "L.E. Cooke Company"], "https://www.lecooke.com/"),
    lead("CA-023", "Agromillora California", "Gridley, CA", "Walnut rootstocks", "Rootstock technology", "Containerized grafted-tree and rootstock supplier with proprietary and licensed walnut programs. Important technology benchmark; likely larger than a typical target.", "https://www.agromillora.com/en-us/our-products/walnuts/", "benchmark", ["Agromillora", "Agromillora California"], "https://www.agromillora.com/"),
    lead("CA-024", "Stuke Nursery Company", "Gridley, CA", "Walnut", "Nursery / germplasm-history", "Long-standing walnut nursery with California germplasm history. Treat as an archival and operating-status diligence lead until current rights and production are confirmed.", "https://bizfileonline.sos.ca.gov/search/business", "verify", ["Stuke Nursery", "Stuke Nursery Co", "Stuke Nursery Company"], ""),
    lead("CA-025", "Baseline Nursery", "Pleasant Grove, CA", "Walnut rootstocks", "Licensed propagator", "UC licensee for multiple walnut varieties and RX1/VX211 rootstocks. A focused northern-Sacramento-Valley propagation lead.", UC_TREE, "review", ["Baseline Nursery"], "https://baselinenursery.com/"),
    lead("CA-026", "Golden Roots Nursery", "Yuba City, CA", "Walnut rootstocks", "Licensed propagator", "UC licensee for RX1 and VX211 walnut rootstocks. A local propagation candidate; verify independent ownership and production scale.", UC_TREE, "verify", ["Golden Roots Nursery"], ""),
    lead("CA-027", "Mazzei Nursery, Inc.", "Fresno, CA", "Vegetable transplants, pistachio and walnut rootstocks", "Propagation", "Family-operated Central Valley vegetable-transplant and tree-rootstock nursery with UC walnut-rootstock licensing. A hybrid annual/perennial nursery model worth mapping.", UC_TREE, "review", ["Mazzei Nursery", "Mazzei Nursery, Inc."], "https://www.tslseed.com/mazzei_nursery_seed.php"),
    lead("CA-028", "Nipama Nursery", "Bakersfield, CA", "Walnut", "Licensed propagator", "UC licensee for Solano walnut. Low-publicity specialist lead requiring operating-status and scale verification.", UC_TREE, "verify", ["Nipama Nursery"], ""),
    lead("CA-029", "Orestimba Nursery", "Crows Landing, CA", "Walnut rootstocks", "Licensed propagator", "UC licensee for multiple walnut varieties and RX1/VX211 rootstocks. Historic records indicate commercial walnut-tree production; refresh current scale during diligence.", UC_TREE, "review", ["Orestimba Nursery", "Orestimba Nursery LLC"], "https://orestimbanursery.wordpress.com/"),
    lead("CA-030", "HMMRHA Pistachio Nursery", "Reedley, CA", "Pistachio", "Licensed propagator", "Commercial pistachio nursery listed by an industry association. Verify current corporate identity and UC-license status before prioritizing outreach.", "https://acpistachios.org/pdf/nurseries.pdf", "verify", ["HMMRHA Pistachio Nursery"], ""),
    lead("CA-031", "McEwen Nursery", "Exeter, CA", "Pistachio", "Licensed propagator", "Commercial pistachio nursery with an established owner/operator contact in industry listings. Confirm current tree program and customer concentration.", "https://acpistachios.org/pdf/nurseries.pdf", "verify", ["McEwen Nursery"], "https://www.mcewen.com/"),
    lead("CA-032", "Pioneer Nursery", "Visalia / Delano, CA", "Pistachio rootstocks", "Rootstock developer / propagator", "Historic pistachio-rootstock developer and nursery. The current commercial entity and active site require direct verification before treating it as an acquisition lead.", "https://www.farmprogress.com/tree-nuts/growing-pistachios-at-pioneer-nursery", "verify", ["Pioneer Nursery"], ""),
    lead("CA-033", "S & J Ranch", "Fresno, CA", "Pistachio", "Propagator / grower", "Commercial pistachio-tree supplier in industry records. Evaluate whether nursery operations are independent of farm management services.", "https://acpistachios.org/pdf/nurseries.pdf", "verify", ["S & J Ranch", "S and J Ranch"], "https://www.sjranchmgmt.com/"),
    lead("CA-034", "Westside Transplant", "Huron / Los Banos, CA", "Pistachio and walnut rootstocks", "Propagation", "Commercial supplier of UCB1 pistachio rootstock and budded trees. A potentially useful permanent-crop propagation platform; clarify ownership and company breadth.", "https://acpistachios.org/pdf/nurseries.pdf", "review", ["Westside Transplant", "Westside Transplant LLC"], ""),
    lead("CA-035", "New Adventure Nursery", "Tulare, CA", "Pistachio", "Licensed propagator", "UC pistachio budding licensee for Famoso, Gumdrop, and Tejon. A focused propagation lead pending business and ownership confirmation.", UC_TREE, "verify", ["New Adventure Nursery", "New Adventure Nursery, Inc"], ""),
    lead("CA-036", "Sweet Darling Sales", "Aptos, CA", "Strawberry", "Breeder / variety owner", "Independent strawberry breeder and variety owner led by Shannon M. Kent. Public plant-patent and Canadian PBR records provide a concrete rights trail; prioritize ownership, portfolio, and succession diligence.", "https://patentimages.storage.googleapis.com/7a/75/f4/2f255f1bcd30d6/USPP29966.pdf", "high", ["Sweet Darling Sales", "Shannon M. Kent", "Shannon Kent"], ""),
    lead("CA-037", "Fruit World Nursery / Blum Agriculture", "Reedley, CA", "Mandarin and specialty citrus", "Nursery / proprietary variety platform", "Family-operated citrus nursery and farming platform with a proprietary-variety orientation. Confirm the legal entities, active variety rights, and whether the nursery platform is separable from farm operations.", "https://www.organicproducenetwork.com/organic-growers/in-their-words-fruit-world-nursery-s-craig-kaprielian", "high", ["Fruit World Nursery", "Blum Agriculture", "Craig Kaprielian"], "https://www.fruitworldco.com/about"),
    lead("CA-038", "Well-Pict Berries", "Watsonville / Oxnard, CA", "Strawberry", "Breeding / growing platform", "California strawberry platform with proprietary-variety breeding and testing activity. Important market benchmark and potential relationship lead; likely requires an explicit size screen before acquisition outreach.", "https://theproducenews.com/well-picts-proprietary-varieties-tailored-district-and-season-0", "benchmark", ["Well-Pict", "Well Pict", "Well-Pict Berries"], "https://www.wellpict.com/"),
    lead("CA-039", "CalVine Nursery", "Shafter, CA", "Grape rootstocks", "Licensed propagator / clean stock", "Small certified grape-rootstock nursery and UC licensee for GRN rootstocks. Clear clean-stock capability; likely a tuck-in or relationship opportunity.", UC_GRAPE, "high", ["CalVine Nursery", "Calvine Nursery, LLC"], "https://www.calvine.com/"),
    lead("CA-040", "Casa Cristal Nursery", "McFarland, CA", "Winegrape and rootstocks", "Licensed propagator", "UC licensee for multiple Pierce's-disease-resistant winegrapes and GRN rootstocks. Relevant commercialization node; verify ownership and financial scale.", UC_GRAPE, "review", ["Casa Cristal Nursery"], "https://casacristal.com/"),
    lead("CA-041", "Dennis and Peter Frick, Inc.", "Bakersfield, CA", "Grape rootstocks", "Licensed propagator", "UC licensee for GRN rootstocks. A propagation and grower-network lead pending confirmation of operating scope.", UC_GRAPE, "verify", ["Dennis and Peter Frick", "Dennis and Peter Frick, Inc"], ""),
    lead("CA-042", "Fratelli Real Estate", "Woodland, CA", "Winegrape and rootstocks", "Licensed propagator / holder unknown", "UC licensee for select PD-resistant winegrapes and GRN rootstocks. The entity name suggests an unusual operating structure, so validate the actual nursery and legal licensee.", UC_GRAPE, "verify", ["Fratelli Real Estate"], ""),
    lead("CA-043", "Guillaume Grapevine Nursery", "Knights Landing, CA", "Winegrape and rootstocks", "Licensed propagator", "Family-run grapevine nursery licensed for all GRN rootstocks. Strong clean-stock and vineyard-supply relationship candidate.", UC_GRAPE, "review", ["Guillaume Grapevine Nursery", "Guillaume Grapevine Nursery, Inc"], "https://guillaumenurseries.com/"),
    lead("CA-044", "Guzman Margaritas Grapevine Nursery", "Fairfield, CA", "Grape rootstocks", "Licensed propagator", "UC licensee for GRN rootstocks. Low-web-visibility propagation lead requiring owner and operating-status diligence.", UC_GRAPE, "verify", ["Guzman Margaritas Grapevine Nursery"], ""),
    lead("CA-045", "Herrick Grapevines", "Red Bluff, CA", "Winegrape", "Licensed propagator", "UC licensee for multiple PD-resistant winegrapes. A commercial vineyard-material supplier and potential regional relationship lead.", UC_GRAPE, "review", ["Herrick Grapevines"], "https://herrickgrapevines.com/"),
    lead("CA-046", "Knights Grapevine Nursery", "Olivehurst, CA", "Grape rootstocks", "Licensed propagator", "Family-operated grapevine nursery licensed for GRN rootstocks. Technical propagation and plant-health process should be part of any visit diligence.", UC_GRAPE, "review", ["Knights Grapevine Nursery", "Knights Grapevine Nursery, Inc"], "https://knightsgrapevinenursery.com/"),
    lead("CA-047", "Martinez Orchards", "Winters, CA", "Grape and walnut rootstocks", "Licensed propagator", "Second-generation grapevine and orchard nursery licensed across UC grape and walnut materials. A serious propagation platform; likely requires scale diligence.", UC_GRAPE, "review", ["Martinez Orchards"], "https://www.martinezorchards.com/"),
    lead("CA-048", "NovaVine Grapevine Nursery", "Santa Rosa, CA", "Winegrape and rootstocks", "Licensed propagator", "UC licensee for PD-resistant winegrapes and all GRN rootstocks. A significant grapevine-propagation ecosystem participant; assess size before acquisition outreach.", UC_GRAPE, "review", ["NovaVine", "NovaVine Grapevine Nursery"], "https://novavine.com/"),
    lead("CA-049", "Sunridge Nurseries", "Bakersfield, CA", "Winegrape, table grape, rootstocks", "Licensed propagator / nursery", "UC licensee for PD-resistant winegrapes and all GRN rootstocks, with vineyard-material and plant-health capability. Strong sector lead; validate ownership and financial fit.", UC_GRAPE, "review", ["Sunridge Nurseries", "Sunridge Nurseries, Inc"], "https://sunridgenurseries.com/"),
    lead("CA-050", "Brown Bag Seed Company", "Bakersfield / Kern County, CA", "Pistachio rootstock seed", "Breeder / seed supplier", "Founder-led pistachio seed and rootstock business with direct technical support and long-standing UCB1 history. Verify which genetics are proprietary, licensed, or public-domain.", "https://www.brownbagseed.com/", "high", ["Brown Bag Seed", "Brown Bag Seed Company", "Kresha Agricultural Nursery"], "https://www.brownbagseed.com/"),
]


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def search_text(record: dict[str, Any]) -> str:
    return normalized(" ".join(str(record.get(field, "")) for field in (
        "assignee", "breeders", "inventors", "title", "tradeName", "cultivar", "notes", "primarySource"
    )))


def matching_records(records: list[dict[str, Any]], aliases: list[str], source: str) -> list[dict[str, Any]]:
    alias_tokens = [normalized(alias) for alias in aliases if len(normalized(alias)) >= 5]
    matches = []
    for record in records:
        haystack = search_text(record)
        if not haystack or not any(alias in haystack for alias in alias_tokens):
            continue
        matches.append({
            "id": record.get("id") or record.get("primarySource") or "",
            "source": source,
            "date": record.get("date") or record.get("issueDate") or record.get("applicationDate") or "",
            "crop": record.get("crop") or "",
            "cultivar": record.get("cultivar") or record.get("title") or "",
            "assignee": record.get("assignee") or "",
            "breeders": record.get("breeders") or "",
            "sourceUrl": record.get("sourceUrl") or record.get("gazetteUrl") or "",
        })
    return matches


def direct_assignee_matches(records: list[dict[str, Any]], aliases: list[str], source: str) -> list[dict[str, Any]]:
    """Return only records whose assignee field supports an ownership signal.

    This deliberately excludes inventor and breeder mentions. CPVO workbook exports
    currently do not carry a consistent holder field, so their name matches remain
    research evidence rather than a legal-owner count.
    """
    alias_tokens = [normalized(alias) for alias in aliases if len(normalized(alias)) >= 5]
    matches = []
    for record in records:
        assignee = normalized(str(record.get("assignee", "")))
        if not assignee or not any(alias in assignee for alias in alias_tokens):
            continue
        matches.append({
            "id": record.get("id") or record.get("primarySource") or "",
            "source": source,
            "date": record.get("date") or record.get("issueDate") or record.get("applicationDate") or "",
            "crop": record.get("crop") or "",
            "cultivar": record.get("cultivar") or record.get("title") or "",
            "assignee": record.get("assignee") or "",
            "sourceUrl": record.get("sourceUrl") or record.get("gazetteUrl") or "",
        })
    return matches


def main() -> None:
    uspto = json.loads(USPTO_PATH.read_text(encoding="utf-8")).get("records", [])
    cpvo = json.loads(CPVO_PATH.read_text(encoding="utf-8")).get("records", [])
    rows = []
    for item in LEADS:
        uspto_matches = matching_records(uspto, item["aliases"], "USPTO")
        cpvo_matches = matching_records(cpvo, item["aliases"], "CPVO")
        direct_uspto_matches = direct_assignee_matches(uspto, item["aliases"], "USPTO")
        all_matches = uspto_matches + cpvo_matches
        item = dict(item)
        item["usptoMatchCount"] = len(uspto_matches)
        item["cpvoMatchCount"] = len(cpvo_matches)
        item["usptoDirectAssigneeCount"] = len(direct_uspto_matches)
        item["directAssigneeRecords"] = direct_uspto_matches[:100]
        item["matchedRecords"] = all_matches[:100]
        if all_matches:
            item["patentReviewStatus"] = "local_register_match_found"
        rows.append(item)
    payload = {
        "metadata": {
            "title": "California Variety Rights Research Pipeline",
            "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
            "recordCount": len(rows),
            "note": "Research leads are distinct from legal ownership profiles. UC license evidence shows authority to propagate/transfer designated material, not ownership of the underlying breeder rights.",
            "sources": ["UC Davis Plant Variety Licensing Program", "Official company websites", "Local USPTO and CPVO dashboard datasets"],
        },
        "records": rows,
    }
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    print(f"Wrote {len(rows)} research leads to {OUTPUT_PATH}")
    print(f"Local USPTO/CPVO matches: {sum(row['usptoMatchCount'] + row['cpvoMatchCount'] for row in rows)}")


if __name__ == "__main__":
    main()
