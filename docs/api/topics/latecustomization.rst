.. _latecustomization:
.. versionadded:: 2

====================
 Late Customization
====================

Late customization allows loading of apps during the first-time experience on
devices.

.. http:get:: /api/v2/latecustomization/?carrier=(str:carrier)&region=(str:region)

  Returns a list of late customization items for this carrier/region.

  **Response**

  :param latecustomization_id: The id for this late-customization item.
  :type latecustomization_id: int
  :param latecustomization_type: Either 'webapp' or 'extension'.
  :type latecustomization_type: str

  Includes the fields for either webapps or extensions, based on the item type.

  :status 200: Successfully completed.


  .. code-block:: json

      {
          "objects": [
              {
                  "latecustomization_type": "webapp",
                  "latecustomization_id": 3,
                  "id": 47911,
                  "slug": "carrier-provided-app-1",
                  ...
              }
              ...
          ]
      }


.. http:post:: /api/v2/latecustomization/

  Create a single late-customization item.

   **Request**

  :param type: Indicates the kind of item: 'webapp' or 'extension'.
  :type type: str
  :param app: A webapp slug, if item is a webapp.
  :type app: str
  :param extension: An extension slug, if item is an extension.
  :type extension: str
  :param region: A region ID.
  :type region: int
  :param carrier: A carrier ID.
  :type carrier: int

  **Response**

  :status 201: Item created.
  :status 403: Not allowed to create this object.


.. http:delete:: /api/v2/latecustomization/(int:id)/

   Remove a late-customization list.

   **Response**

   :status 204: Successfully completed.
   :status 403: Not allowed to access this object.
