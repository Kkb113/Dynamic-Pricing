from audit.relationship_audit import LOGICAL_RELATIONSHIPS


def test_all_29_phase2_critical_logical_relationships_are_registered():
    assert len(LOGICAL_RELATIONSHIPS) == 29
    names={row[0] for row in LOGICAL_RELATIONSHIPS}
    assert {
        "SalesOrder_Customer", "SalesOrder_Store", "SalesLine_Order", "SalesLine_Product",
        "Browsing_Customer", "Browsing_Product", "Cart_Customer", "Cart_Product",
        "Search_Customer", "Product_Category", "Product_Brand", "Customer_Region", "Store_Region",
    } <= names


def test_logical_relationship_definitions_are_unique():
    names=[row[0] for row in LOGICAL_RELATIONSHIPS]
    assert len(names)==len(set(names))
