"""The integration must use the vendored Ascend-API library, never PyPI's 0.7.1."""
import sys

VENDOR = "custom_components.southern_company._vendor.southern_company_api"


def test_vendored_package_is_importable_and_self_contained():
    from custom_components.southern_company._vendor import southern_company_api as lib

    assert lib.__name__ == VENDOR
    # parser.py's former absolute import must now resolve inside the vendored package
    assert lib.parser.Account is lib.account.Account
    assert lib.parser.Account.__module__ == f"{VENDOR}.account"


def test_integration_modules_import_the_vendored_library():
    from custom_components.southern_company import config_flow, coordinator, sensor, statistics
    from custom_components.southern_company._vendor import southern_company_api as lib

    assert config_flow.SouthernCompanyAPI is lib.SouthernCompanyAPI
    assert coordinator.southern_company_api is lib
    assert sensor.southern_company_api is lib
    assert statistics.southern_company_api is lib
    assert "southern_company_api" not in sys.modules  # PyPI package never imported
