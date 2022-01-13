Work in Progress.

# Development

To run the server locally, (optionally) create a new Python virtualenv of your preferred flavor and
install the dependencies.

```shell
make init
# or `make update` if you'd also like to update dependencies to latest permissible versions.
```

Initialize/supply [ARK](https://arks.org/) maps.
```shell
# This is sufficient to get started.
cp ark_map.example.csv ark_map.csv
cp ark_naan_shoulder_map.example.csv ark_naan_shoulder_map.csv
```

You can then run the server with:

```shell
export $(grep -v '^#' .env | xargs)
make up-dev
```

## Example queries:

-   To get an HTML response:

    ```shell
    curl http://localhost:8000/ark:57802/2021/11/marda/phonons/material_id
    # Explicitly request HTML (not an owl:Ontology, so won't actually return HTML):
    curl -H "Accept: text/html" http://localhost:8000/ark:57802/2021/11/marda/phonons/material_id
    # Explicitly request HTML
    curl -H "Accept: text/html" http://localhost:8000/ark:57802/2021/11/marda/phonons
    ```

    or alternatively just visit http://localhost:8000/ark:57802/2021/11/marda/phonons/material_id (or
    http://localhost:8000/ark:57802/2021/11/marda/phonons) in your browser with the server running.

-   To get responses in various RDF formats:

    ```shell
    # A readable, hand-editable RDF format ("turse [sic] triples")
    curl -H "Accept: text/turtle" http://localhost:8000/ark:57802/2021/11/marda/phonons/material_id
    # JSON-LD
    curl -H "Accept: application/ld+json" http://localhost:8000/ark:57802/2021/11/marda/phonons/material_id
    # XML
    curl -H "Accept: application/rdf+xml" http://localhost:8000/ark:57802/2021/11/marda/phonons/material_id
    ```

    You can request any [rdflib-compatible format or
    mime-type](https://rdflib.readthedocs.io/en/stable/plugin_serializers.html), e.g.,
    `application/rdf+xml`, `nquads`, etc., via the `Accept` header.
    
    You may also use the [RFC 7231](https://tools.ietf.org/html/rfc7231#section-5.3.2)
    `Accept` header standard to indicate acceptable alternatives with relative quality factors. For
    example,
    
    ```shell
    curl -H "Accept: text/html;q=0.5,text/turtle;q=0.8,application/ld+json" \
        http://localhost:8000/ark:57802/2021/11/marda/phonons/material_id
    ```
    
    indicates that you prefer JSON-LD (`q=1` is implicit if unstated); if JSON-LD isn't available,
    your next preference is Turtle; and if Turtle isn't available, you prefer HTML to any other
    format.

# Notes (currently, a braindump)

`termeric` is a tool for term *e*gress, *r*evision, and *i*ngress — *c*alendarized.

- *terms*: full-copy JSON-LD docs of metadata (so @context expected). Optional owl:equivalentClass
  or owl:equivalentProperty statement relating to a past-month term in this termeric repo, if this
  term was imported; this statement gets removed if the imported term is changed at all.

- *namespaces* - JSON-LD docs of metadata about term namespaces (the part before the last `/` of a
  term URL, an org/repo qualified by yyyy/mm and by ark naan). Should be `a owl:Ontology .`

- *agents*: users and their software agents that authenticate and CRUD resources. PLEASE just use
  HTTP Basic Auth. FastAPI has good support and documentation for it. You can store passwords hashed
  in mongo using the method given in the FastAPI docs for storing passwords for OAuth2. (canAdmin :
  List[Union(Org, Repo)]], canEdit : List[Repo], name : str, hashedPwd : str, @id, @type :
  Union[Person, SoftwareAgent]). A Person can CRUD SoftwareAgent agents that canEdit repos that the
  person canAdmin (directly or if canAdmin the repo's org). No one can edit the past.  Example agent
  @id: <https://ns.polyneme.xyz/ark:57802/9999/12/system/agents/donny>. `9999/12/` is the convention
  for org/repo terms that can change at any time. If you canEdit a repo, that applies for the current
  month and any future month. An agent can CRUD any and all non-admin software agents with a subset of
  their canEdit potential. However, only person agents that canAdmin can CRUD other person agents.

- *touches*: a simple relation: (term, agent, timestamp)