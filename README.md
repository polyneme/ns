Work in Progress.

Tiny demo at <https://ns.polyneme.xyz/2021/04/marda-dd/test#helloWorld>

# Development

To run the server locally, (optionally) create a new Python virtualenv of your preferred flavor and install the dependencies.

```shell
pip install -r requirements
```

You can then run the server with:

```shell
uvicorn --reload --port=8000 main:app
```

## Example queries:

-   To get an HTML response:

    ```shell
    curl http://localhost:8000/2021/04/marda-dd/test#helloWorld
    # Explicitly request HTML
    curl -H "Accept: text/html" http://localhost:8000/2021/04/marda-dd/test#helloWorld
    ```

    or alternatively just visit http://localhost:8000/2021/04/marda-dd/test#helloWorld in your
    browser with the server running.

-   To get responses in various RDF formats:

    ```shell
    # A readable, hand-editable RDF format ("turse [sic] triples")
    curl -H "Accept: text/turtle" http://localhost:8000/2021/04/marda-dd/test#helloWorld
    # JSON-LD
    curl -H "Accept: application/ld+json" http://localhost:8000/2021/04/marda-dd/test#helloWorld
    # XML
    curl -H "Accept: application/rdf+xml" http://localhost:8000/2021/04/marda-dd/test#helloWorld
    ```

    You can request any [rdflib-compatible format or
    mime-type](https://rdflib.readthedocs.io/en/stable/plugin_serializers.html), e.g.,
    `application/rdf+xml`, `nquads`, etc., via the `Accept` header.
    
    You may also use the [RFC 7231](https://tools.ietf.org/html/rfc7231#section-5.3.2)
    `Accept` header standard to indicate acceptable alternatives with relative quality factors. For
    example,
    
    ```shell
    curl -H "Accept: text/html;q=0.5,text/turtle;q=0.8,application/ld+json" \
        http://localhost:8000/2021/04/marda-dd/test#helloWorld
    ```
    
    indicates that you prefer JSON-LD (`q=1` is implicit if unstated); if JSON-LD isn't available,
    your next preference is Turtle; and if Turtle isn't available, you prefer HTML to any other
    format.

# References

* [Best Practice Recipes for Publishing RDF Vocabularies -- Recipe 3. Extended configuration for a
 'hash namespace'](https://www.w3.org/TR/2008/NOTE-swbp-vocab-pub-20080828/#recipe3)
  
* [Is 303 Really Necessary?](https://blog.iandavis.com/2010/11/is-303-really-necessary/)
