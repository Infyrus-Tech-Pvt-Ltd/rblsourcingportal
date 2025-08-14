/// <reference path="../pb_data/types.d.ts" />
migrate((app) => {
  const collection = app.findCollectionByNameOrId("pbc_2223581722")

  // update collection data
  unmarshal({
    "name": "customers"
  }, collection)

  return app.save(collection)
}, (app) => {
  const collection = app.findCollectionByNameOrId("pbc_2223581722")

  // update collection data
  unmarshal({
    "name": "Customers"
  }, collection)

  return app.save(collection)
})
