import config
import logging
import requests


class Rubie:
    @staticmethod
    def is_connected()-> bool:
        try:
            response = requests.get(f"{config.rubie_base_url()}/sha", timeout=5)
            if response.status_code == 200:
                return True
            else:
                logging.warning("Rubie connection check failed with status code: %s", response.status_code)
                return False
        except requests.RequestException as e:
            logging.warning("Error connecting to Rubie: %s", e)
            return False
