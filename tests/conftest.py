def pytest_configure(config):
    config.addinivalue_line("markers", "at: acceptance test (AT-xx)")
