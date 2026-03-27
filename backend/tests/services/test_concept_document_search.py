import json

from app.services.concept_document_search import ConceptDocumentSearchService, parse_query_intent


def make_document(**overrides):
    base = {
        "document_id": "doc-1",
        "concept_document_id": "concept-1",
        "source_system": "concept",
        "file_name": "Generator Service Sheet.pdf",
        "file_extension": "pdf",
        "file_path": "Fairlands/Energy Centre/Generator 1/Generator Service Sheet.pdf",
        "open_url": "https://concept.example/open/1",
        "download_url": "https://concept.example/download/1",
        "site_id": "site-002",
        "site_name": "Fairlands",
        "building_id": "site-002",
        "building_name": "Fairlands",
        "discipline": "electrical",
        "equipment_category": "generator",
        "equipment_name": "Generator 1",
        "document_type": "service sheet",
        "document_date": "2025-05-01",
        "tags": ["generator", "service"],
        "cleaned_text": "Generator 1 quarterly service sheet with inspection results.",
        "extracted_text": "Generator 1 quarterly service sheet with inspection results.",
        "path": "Fairlands / Energy Centre / Generator 1",
    }
    base.update(overrides)
    return base


def test_parse_generator_service_sheets():
    intent = parse_query_intent("generator service sheets 2023")
    assert intent["document_type"] == "service_sheet"
    assert intent["equipment"] == "generator"
    assert intent["year"] == 2023
    assert intent["frequency"] is None


def test_parse_generator_inspection_sheets():
    intent = parse_query_intent("generator inspection sheets 2024")
    assert intent["document_type"] == "inspection_sheet"
    assert intent["equipment"] == "generator"
    assert intent["year"] == 2024


def test_parse_common_generator_typo():
    intent = parse_query_intent("generagor sheets 2025")
    assert intent["equipment"] == "generator"
    assert intent["year"] == 2025


def test_parse_pressure_vessel_certificate():
    intent = parse_query_intent("pressure vessel certificate")
    assert intent["document_type"] == "certificate"
    assert intent["equipment"] == "pressure_vessel"


def test_parse_meter_readings_2024():
    intent = parse_query_intent("meter readings 2024")
    assert intent["document_type"] == "reading"
    assert intent["year"] == 2024


def test_parse_monthly_inspection_plumbing():
    intent = parse_query_intent("monthly inspection plumbing february 2025")
    assert intent["discipline"] == "plumbing"
    assert intent["document_type"] == "inspection_sheet"
    assert intent["month"] == 2
    assert intent["year"] == 2025


def test_prefers_latest_generator_service_sheet(tmp_path):
    index_path = tmp_path / "concept_documents.json"
    older = make_document(
        document_id="doc-older",
        concept_document_id="concept-older",
        title="Generator Service Sheet 2024.pdf",
        document_date="2024-02-01",
        open_url="https://concept.example/open/older",
    )
    newer = make_document(
        document_id="doc-newer",
        concept_document_id="concept-newer",
        title="Generator Service Sheet 2025.pdf",
        document_date="2025-05-01",
        open_url="https://concept.example/open/newer",
    )
    unrelated = make_document(
        document_id="doc-other",
        concept_document_id="concept-other",
        title="Lift Annual Inspection Certificate 2025.pdf",
        document_type="certificate",
        equipment_category="elevator",
        equipment_name="Lift 2",
        discipline="vertical transport",
        cleaned_text="Annual lift inspection certificate for Lift 2.",
        extracted_text="Annual lift inspection certificate for Lift 2.",
        path="Fairlands / Vertical Transport / Lift 2",
        file_path="Fairlands/Vertical Transport/Lift 2/Lift Annual Inspection Certificate 2025.pdf",
        open_url="https://concept.example/open/lift",
    )

    index_path.write_text(json.dumps([older, newer, unrelated]), encoding="utf-8")
    service = ConceptDocumentSearchService(index_path=index_path)

    response = service.search(
        site_id="site-002", building_id="site-002", query="last generator service sheets", top_k=5
    )

    assert response["total_results"] == 2
    assert response["results"][0]["document_id"] == "doc-newer"
    assert response["results"][1]["document_id"] == "doc-older"


def test_filters_to_year_and_lift_documents(tmp_path):
    index_path = tmp_path / "concept_documents.json"
    lift_2024 = make_document(
        document_id="doc-lift-2024",
        concept_document_id="concept-lift-2024",
        title="Lift Annual Inspection Certificate 2024.pdf",
        document_type="certificate",
        equipment_category="elevator",
        equipment_name="Lift 2",
        discipline="vertical transport",
        document_date="2024-01-14",
        cleaned_text="Annual lift inspection certificate issued for Lift 2.",
        extracted_text="Annual lift inspection certificate issued for Lift 2.",
        path="Fairlands / Vertical Transport / Lift 2",
        file_path="Fairlands/Vertical Transport/Lift 2/Lift Annual Inspection Certificate 2024.pdf",
        open_url="https://concept.example/open/lift-2024",
    )
    lift_2025 = make_document(
        document_id="doc-lift-2025",
        concept_document_id="concept-lift-2025",
        title="Lift Annual Inspection Certificate 2025.pdf",
        document_type="certificate",
        equipment_category="elevator",
        equipment_name="Lift 2",
        discipline="vertical transport",
        document_date="2025-01-14",
        cleaned_text="Annual lift inspection certificate issued for Lift 2.",
        extracted_text="Annual lift inspection certificate issued for Lift 2.",
        path="Fairlands / Vertical Transport / Lift 2",
        file_path="Fairlands/Vertical Transport/Lift 2/Lift Annual Inspection Certificate 2025.pdf",
        open_url="https://concept.example/open/lift-2025",
    )
    generator = make_document(
        document_id="doc-generator",
        concept_document_id="concept-generator",
        title="Generator Service Sheet 2024.pdf",
        document_date="2024-04-04",
        open_url="https://concept.example/open/generator",
    )

    index_path.write_text(json.dumps([lift_2024, lift_2025, generator]), encoding="utf-8")
    service = ConceptDocumentSearchService(index_path=index_path)

    response = service.search(
        site_id="site-002",
        building_id="site-002",
        query="elevator annual lift inspection certificate for 2024",
        top_k=5,
    )

    assert response["total_results"] == 1
    assert response["results"][0]["document_id"] == "doc-lift-2024"
    assert response["results"][0]["match_reasons"]


def test_loads_tsv_export_and_normalises_site_scope(tmp_path):
    index_path = tmp_path / "concept_export.tsv"
    index_path.write_text(
        "\t".join(
            [
                "site_id",
                "Building",
                "Document Sub Class",
                "Document Ref.",
                "Title",
                "Author",
                "Category",
                "Subject",
                "Repository Description",
                "Created Date",
                "Expiry Date",
                "Actual Path",
                "Concept Document Id",
                "Filename",
                "",
            ]
        )
        + "\n"
        + "\t".join(
            [
                "001",
                "Fairlands",
                "Operations Compliance GMR_ELECTRICAL",
                "Fairlands generator service 2023",
                "Generator Service Sheet 2023",
                "REMS",
                "Electrical",
                "Monthly generator service sheet",
                (
                    r"Operations Compliance GMR_ELECTRICAL: \\BMS-RBPADMZCEPT\E$\DMS"
                    r"\FNB REMS Buildings\Operations Compliance GMR\ELECTRICAL"
                ),
                "2023/12/20 09:30",
                "",
                (
                    r"\\BMS-RBPADMZCEPT\E$\DMS\FNB REMS Buildings\Operations Compliance GMR"
                    r"\ELECTRICAL\00\000003\generator-service-2023.pdf"
                ),
                "35999",
                "generator service 2023.pdf",
                "",
            ]
        )
        + "\n"
        + "\t".join(
            [
                "002",
                "Sandton",
                "Operations Compliance GMR_ELECTRICAL",
                "Other site generator service 2023",
                "Generator Service Sheet 2023",
                "REMS",
                "Electrical",
                "Monthly generator service sheet",
                r"Operations Compliance GMR_ELECTRICAL: \\BMS-RBPADMZCEPT\E$\DMS\Other Site\ELECTRICAL",
                "2023/12/21 09:30",
                "",
                r"\\BMS-RBPADMZCEPT\E$\DMS\Other Site\ELECTRICAL\00\000003\generator-service-2023.pdf",
                "36000",
                "generator service 2023.pdf",
                "",
            ]
        ),
        encoding="utf-8",
    )

    service = ConceptDocumentSearchService(index_path=index_path)

    response = service.search(
        site_id="site-001",
        building_id="site-001",
        query="generator service sheets for 2023",
        top_k=5,
    )

    assert response["total_results"] == 1
    assert response["results"][0]["document_id"] == "35999"
    assert response["results"][0]["building_name"] == "Fairlands"
    assert response["results"][0]["document_type"] == "service sheet"
    assert response["results"][0]["equipment_category"] == "generator"
    assert (
        response["results"][0]["open_url"]
        == "https://remsconcept.fnb.co.za/Evolution/!System/Documents/ConceptDocument/"
        "ViewConceptDocumentItem.aspx?__referrer=%2FEvolution%2F!System%2FDocuments%2FConceptDocument%2F"
        "ViewConceptDocumentItems.aspx&id=35999&PrimaryEntity=&PrimaryKeyId=-1"
    )
    assert response["results"][0]["download_url"] is not None
    assert "generator" in response["results"][0]["match_reasons"]


def test_requires_exact_document_type_when_available(tmp_path):
    index_path = tmp_path / "concept_documents.json"
    service_sheet = make_document(
        document_id="doc-service-sheet",
        concept_document_id="concept-service-sheet",
        title="Generator diesel reading March 2024.pdf",
        document_type="service sheet",
        document_date="2024-03-11",
        open_url="https://concept.example/open/service-sheet",
    )
    inspection_sheet = make_document(
        document_id="doc-inspection-sheet",
        concept_document_id="concept-inspection-sheet",
        title="Generator weekly inspection March 2024.pdf",
        file_name="Generator weekly inspection March 2024.pdf",
        file_path="Fairlands/Energy Centre/Generator 1/Generator weekly inspection March 2024.pdf",
        document_type="inspection sheet",
        document_date="2024-03-04",
        tags=["generator", "inspection"],
        cleaned_text="Generator 1 weekly inspection results.",
        extracted_text="Generator 1 weekly inspection results.",
        open_url="https://concept.example/open/inspection-sheet",
    )

    index_path.write_text(json.dumps([service_sheet, inspection_sheet]), encoding="utf-8")
    service = ConceptDocumentSearchService(index_path=index_path)

    response = service.search(
        site_id="site-002",
        building_id="site-002",
        query="generator service sheets 2024",
        top_k=10,
    )

    assert response["total_results"] == 1
    assert response["results"][0]["document_id"] == "doc-service-sheet"
    assert response["results"][0]["document_type"] == "service sheet"


def test_monthly_inspection_plumbing_february(tmp_path):
    index_path = tmp_path / "concept_documents.json"
    plumbing_inspection = make_document(
        document_id="doc-plumbing-2025",
        concept_document_id="concept-plumbing-2025",
        title="Plumbing Monthly Inspection Feb 2025.pdf",
        document_type="inspection sheet",
        document_date="2025-01-30",
        equipment_category="plumbing",
        discipline="plumbing",
        equipment_name="Plumbing riser",
        cleaned_text="Monthly plumbing inspection with February callout.",
        extracted_text="Monthly plumbing inspection with February callout.",
        open_url="https://concept.example/open/plumbing-2025",
    )
    unrelated = make_document(
        document_id="doc-plumbing-2025b",
        concept_document_id="concept-plumbing-2025b",
        title="Plumbing Inspection March 2025.pdf",
        document_type="inspection sheet",
        document_date="2025-03-05",
        equipment_category="plumbing",
        discipline="plumbing",
        equipment_name="Plumbing riser",
        open_url="https://concept.example/open/plumbing-2025b",
    )

    index_path.write_text(json.dumps([plumbing_inspection, unrelated]), encoding="utf-8")
    service = ConceptDocumentSearchService(index_path=index_path)

    response = service.search(
        site_id="site-002",
        building_id="site-002",
        query="monthly inspection plumbing february 2025",
        top_k=5,
    )

    assert response["total_results"] == 1
    assert response["results"][0]["document_id"] == "doc-plumbing-2025"


def test_tsv_import_derives_normalized_metadata(tmp_path):
    index_path = tmp_path / "concept_export.tsv"
    index_path.write_text(
        (
            "site_id\tBuilding\tDocument Sub Class\tDocument Ref.\tTitle\tAuthor\tCategory\tSubject\t"
            "Repository Description\tCreated Date\tExpiry Date\tActual Path\tConcept Document Id\tFilename\n"
        )
        + (
            "001\tFairlands\tOperations Compliance GMR_ELECTRICAL\tFairlands generator service 2023\t"
            "Generator Service Sheet 2023\tREMS\tService\tGenerator service summary\t"
            "Operations Compliance GMR_ELECTRICAL: \\BMS-RBPADMZCEPT\\E$\\DMS\\FNB REMS Buildings\\"
            "Operations Compliance GMR\\ELECTRICAL\t2023/05/18 10:00\t2024/05/18 00:00\t"
            "\\BMS-RBPADMZCEPT\\E$\\DMS\\FNB REMS Buildings\\Operations Compliance GMR\\ELECTRICAL\\01\\000001\\"
            "service-sheet.pdf\t12345\tGenerator Service Sheet 2023.pdf\n"
        )
    )

    service = ConceptDocumentSearchService(index_path=index_path)
    response = service.search(site_id="site-001", building_id="site-001", query="generator service sheet 2023", top_k=1)
    assert response["total_results"] == 1
    result = response["results"][0]
    assert result["normalized_document_type"] == "service_sheet"
    assert result["normalized_equipment"] == "generator"
    assert result["normalized_discipline"] == "electrical"
    assert result["normalized_year"] == 2023
    assert (
        result["concept_url"]
        == "https://remsconcept.fnb.co.za/Evolution/!System/Documents/ConceptDocument/"
        "ViewConceptDocumentItem.aspx?__referrer=%2FEvolution%2F!System%2FDocuments%2FConceptDocument%2F"
        "ViewConceptDocumentItems.aspx&id=12345&PrimaryEntity=&PrimaryKeyId=-1"
    )
