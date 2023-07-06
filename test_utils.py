import pytest

from utils import (extract_url_list)

def test_extract_url_list_simple_link():
    text = "<@U05AHRCAXTL> can you summarize this <https://en.wikipedia.org/wiki/Doom_book>"

    url_list = extract_url_list(text)
    assert url_list != None
    assert len(url_list) == 1

# def test_extract_url_list_hyperlink():
#     '''
#     FAILURE: this parser is not able to see the link within a slack-style syntax
#     '''
#     text = "<@U05AHRCAXTL> can you summarize this <https://en.wikipedia.org/wiki/Doom_book|wikipedia page>"

#     url_list = extract_url_list(text)
#     assert url_list != None
#     assert len(url_list) == 1

def test_extract_url_list_pdf_link():
    text = "<@U05AHRCAXTL> are you able to access this <https://hartfordhealthcare.org/file%20library/chna/chna-hartford-hospital-2022.pdf?_ga=2.248866113.710713768.1687980028-1118602651.1687980028&amp;_gl=1*depsgg*_ga*MTExODYwMjY1MS4xNjg3OTgwMDI4*_ga_4604MZZMMD*MTY4Nzk4MDAyOC4xLjAuMTY4Nzk4MDA0My40NS4wLjA>."

    url_list = extract_url_list(text)
    assert url_list != None
    assert len(url_list) == 1    

def test_extract_url_list_pdf_hyperlink():
    text = "<@U05AHRCAXTL> are you able to access this <https://hartfordhealthcare.org/file%20library/chna/chna-hartford-hospital-2022.pdf?_ga=2.248866113.710713768.1687980028-1118602651.1687980028&amp;_gl=1*depsgg*_ga*MTExODYwMjY1MS4xNjg3OTgwMDI4*_ga_4604MZZMMD*MTY4Nzk4MDAyOC4xLjAuMTY4Nzk4MDA0My40NS4wLjA.|2022 Community Health Needs Assessment>"

    url_list = extract_url_list(text)
    assert url_list != None
    assert len(url_list) == 1    


# def test_extract_url_list():
#     '''
#     the extract_url_list function does not return when given this text
#     '''
#     text = "<@U05AHRCAXTL> please identify opportunities that a patient engagement software company, specifically, <https://cipherhealth.com/|CipherHealth> has to support Hartford Healthcare, based on their <https://hartfordhealthcare.org/file%20library/chna/chna-hartford-hospital-2022.pdf?_ga=2.248866113.710713768.1687980028-1118602651.1687980028&amp;_gl=1*depsgg*_ga*MTExODYwMjY1MS4xNjg3OTgwMDI4*_ga_4604MZZMMD*MTY4Nzk4MDAyOC4xLjAuMTY4Nzk4MDA0My40NS4wLjA.|2022 Community Health Needs Assessment> which outlines their plans to improve the lives of their community."

#     url_list = extract_url_list(text)
#     #NEVER RETURNS

#     assert url_list == None




