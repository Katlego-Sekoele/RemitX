"""Every cache namespace, in one place.

A cached read and the writes that invalidate it often live in different route
modules. Naming the namespace here means they cannot spell it differently.
"""


class Namespace:
    # GET /kyc/reference. The same for everyone; only migrations change it.
    KYC_REFERENCE = "kyc-reference"
    # GET /beneficiaries/get-beneficiary-list, per caller and sort order.
    BENEFICIARY_LIST = "beneficiary-list"
