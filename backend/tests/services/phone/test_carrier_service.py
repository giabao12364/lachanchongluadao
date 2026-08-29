from app.services.phone.carrier_service import get_carrier, UNKNOWN_CARRIER 


class TestGetCarrier: 
    def test_viettel_098(self): 
        # Ví dụ mẫu chính xác từ task: "098→Viettel" 
        assert get_carrier("+84987654321") == "Viettel" 

    def test_viettel_032(self): 
        assert get_carrier("+84321234567") == "Viettel" 

    def test_vinaphone_091(self): 
        assert get_carrier("+84912345678") == "Vinaphone" 

    def test_mobifone_090(self): 
        assert get_carrier("+84901234567") == "Mobifone" 

    def test_vietnamobile_092(self):
        assert get_carrier("+84921234567") == "Vietnamobile" 

    def test_gmobile_099(self):
        assert get_carrier("+84991234567") == "Gmobile" 

    def test_unknown_prefix_returns_khong_xac_dinh(self): 
        # Ví dụ mẫu từ task: "lạ→Không xác định" (BR-02-2: không báo lỗi) 
        assert get_carrier("+84199999999") == UNKNOWN_CARRIER 

    def test_none_returns_khong_xac_dinh(self): 
        assert get_carrier(None) == UNKNOWN_CARRIER 

    def test_empty_string_returns_khong_xac_dinh(self): 
        assert get_carrier("") == UNKNOWN_CARRIER 

    def test_wrong_country_code_returns_khong_xac_dinh(self):
        assert get_carrier("+1912345678") ==  UNKNOWN_CARRIER

    def test_too_short_returns_khong_xac_dinh(self):
        assert get_carrier("+849")== UNKNOWN_CARRIER